import 'dart:convert';
import 'dart:io';
import 'dart:math';

// ── 설정 ──────────────────────────────────────────────────────
// 로컬 테스트: 'http://127.0.0.1:8000'
// ECS 배포 후: ALB DNS 주소
const String baseUrl = 'http://127.0.0.1:8000';

/// AWS Lambda API Gateway — presigned URL 발급 엔드포인트
/// stage 이름은 AWS 콘솔 API Gateway → chatda-api → 스테이지 탭에서 확인
const String lambdaUrl =
    'https://eikuvtkwdd.execute-api.ap-northeast-2.amazonaws.com/prod/presigned-url';

// ── 전역 상태 ──────────────────────────────────────────────────
String? _accessToken;
int? _lostItemId;
int? _foundItemId;
int? _matchId;

// ══════════════════════════════════════════════════════════════
// 로깅 헬퍼
// ══════════════════════════════════════════════════════════════

String _ts() {
  final n = DateTime.now();
  return '[${n.hour.toString().padLeft(2, '0')}:'
      '${n.minute.toString().padLeft(2, '0')}:'
      '${n.second.toString().padLeft(2, '0')}.'
      '${n.millisecond.toString().padLeft(3, '0')}]';
}

void _log(String msg) => print('${_ts()} $msg');

void _logSection(String title) {
  final bar = '─' * 55;
  print('\n${_ts()} $bar');
  print('${_ts()} ▶ $title');
  print('${_ts()} $bar');
}

void _logReq(String method, String url, {Object? body}) {
  _log('  ↑ $method $url');
  if (body != null) {
    final pretty = const JsonEncoder.withIndent('      ').convert(body);
    _log('    body: $pretty');
  }
}

void _logFormFields(Map<String, String> fields) {
  _log('  ↑ multipart/form-data fields:');
  for (final e in fields.entries) {
    final val = e.value.length > 80 ? '${e.value.substring(0, 80)}...' : e.value;
    _log('      ${e.key}: $val');
  }
}

void _logRes(int status, Map<String, dynamic> res, Duration elapsed) {
  final ok = status < 300;
  _log('  ↓ ${ok ? '✅' : '❌'} HTTP $status  (+${elapsed.inMilliseconds}ms)');
  final pretty = const JsonEncoder.withIndent('      ').convert(res);
  for (final line in pretty.split('\n')) {
    _log('    $line');
  }
}

void _logS3Result(String key, int bytes, int status, Duration elapsed) {
  _log(
    '  ↓ ${status < 300 ? '✅' : '❌'} S3 PUT  HTTP $status'
    '  (${bytes ~/ 1024} KB, +${elapsed.inMilliseconds}ms)',
  );
  _log('    s3_key: $key');
}

// ══════════════════════════════════════════════════════════════
// HTTP 헬퍼
// ══════════════════════════════════════════════════════════════

/// FastAPI 서버에 JSON 요청
Future<Map<String, dynamic>> _jsonRequest(
  String method,
  String path, {
  Map<String, dynamic>? body,
  bool auth = false,
}) async {
  final url = '$baseUrl$path';
  _logReq(method, url, body: body);

  final sw = Stopwatch()..start();
  final client = HttpClient();
  final uri = Uri.parse(url);

  HttpClientRequest req;
  switch (method) {
    case 'POST':
      req = await client.postUrl(uri);
      break;
    case 'PATCH':
      req = await client.patchUrl(uri);
      break;
    case 'DELETE':
      req = await client.deleteUrl(uri);
      break;
    case 'PUT':
      req = await client.putUrl(uri);
      break;
    default:
      req = await client.getUrl(uri);
  }

  req.headers.set('Content-Type', 'application/json; charset=utf-8');
  if (auth && _accessToken != null) {
    req.headers.set('Authorization', 'Bearer $_accessToken');
  }
  if (body != null) {
    final encoded = utf8.encode(jsonEncode(body));
    req.headers.contentLength = encoded.length;
    req.add(encoded);
  }

  final res = await req.close();
  final resBody = await res.transform(utf8.decoder).join();
  client.close();
  sw.stop();

  final Map<String, dynamic> result;
  if (resBody.isEmpty) {
    result = {'statusCode': res.statusCode};
  } else {
    final decoded = jsonDecode(resBody);
    result = {
      'statusCode': res.statusCode,
      ...(decoded is Map<String, dynamic> ? decoded : {'body': decoded}),
    };
  }
  _logRes(res.statusCode, result, sw.elapsed);
  return result;
}

/// Lambda API Gateway에 JSON POST
Future<Map<String, dynamic>> _lambdaRequest(Map<String, dynamic> body) async {
  _logReq('POST', lambdaUrl, body: body);
  final sw = Stopwatch()..start();

  final client = HttpClient();
  final req = await client.postUrl(Uri.parse(lambdaUrl));
  req.headers.set('Content-Type', 'application/json; charset=utf-8');
  final encoded = utf8.encode(jsonEncode(body));
  req.headers.contentLength = encoded.length;
  req.add(encoded);

  final res = await req.close();
  final resBody = await res.transform(utf8.decoder).join();
  client.close();
  sw.stop();

  final Map<String, dynamic> result;
  if (resBody.isEmpty) {
    result = {'statusCode': res.statusCode};
  } else {
    final decoded = jsonDecode(resBody);
    // Lambda API Gateway는 body 필드 안에 실제 JSON을 문자열로 줄 수 있음
    if (decoded is Map<String, dynamic> && decoded.containsKey('body')) {
      final inner = decoded['body'];
      final innerMap = inner is String ? jsonDecode(inner) as Map<String, dynamic> : inner as Map<String, dynamic>;
      result = {'statusCode': res.statusCode, ...innerMap};
    } else {
      result = {
        'statusCode': res.statusCode,
        ...(decoded is Map<String, dynamic> ? decoded : {'body': decoded}),
      };
    }
  }
  _logRes(res.statusCode, result, sw.elapsed);
  return result;
}

/// S3 presigned URL에 이미지 바이너리 직접 PUT
Future<int> _s3PutUpload(
  String presignedUrl,
  List<int> imageBytes,
  String contentType,
) async {
  final uploadUrl = presignedUrl;
  final baseKey = uploadUrl.split('?').first;
  _log('  ↑ PUT $baseKey  (presigned, ${imageBytes.length ~/ 1024} KB)');
  _log('    Content-Type: $contentType');

  final sw = Stopwatch()..start();
  final client = HttpClient();
  final req = await client.putUrl(Uri.parse(uploadUrl));
  req.headers.set('Content-Type', contentType);
  req.headers.contentLength = imageBytes.length;
  req.add(imageBytes);

  final res = await req.close();
  sw.stop();

  // 실패 시 S3 오류 메시지(XML) 출력
  if (res.statusCode >= 300) {
    final body = await res.transform(utf8.decoder).join();
    _log('  S3 오류 응답: $body');
  } else {
    await res.drain<void>();
  }
  client.close();

  _logS3Result(baseKey.split('/').skip(3).join('/'), imageBytes.length, res.statusCode, sw.elapsed);
  return res.statusCode;
}

/// FastAPI 서버에 multipart/form-data POST (텍스트 필드만)
Future<Map<String, dynamic>> _multipartRequest(
  String path,
  Map<String, String> fields, {
  bool auth = false,
}) async {
  final url = '$baseUrl$path';
  _logFormFields(fields);

  final sw = Stopwatch()..start();
  final boundary = '----DartBoundary${Random().nextInt(999999)}';
  final client = HttpClient();
  final req = await client.postUrl(Uri.parse(url));

  req.headers.set('Content-Type', 'multipart/form-data; boundary=$boundary');
  if (auth && _accessToken != null) {
    req.headers.set('Authorization', 'Bearer $_accessToken');
  }

  final bodyBytes = <int>[];
  fields.forEach((key, value) {
    bodyBytes.addAll(utf8.encode('--$boundary\r\n'));
    bodyBytes.addAll(utf8.encode('Content-Disposition: form-data; name="$key"\r\n'));
    bodyBytes.addAll(utf8.encode('Content-Type: text/plain; charset=utf-8\r\n\r\n'));
    bodyBytes.addAll(utf8.encode(value));
    bodyBytes.addAll(utf8.encode('\r\n'));
  });
  bodyBytes.addAll(utf8.encode('--$boundary--\r\n'));

  req.headers.contentLength = bodyBytes.length;
  req.add(bodyBytes);

  final res = await req.close();
  final resBody = await res.transform(utf8.decoder).join();
  client.close();
  sw.stop();

  final Map<String, dynamic> result;
  if (resBody.isEmpty) {
    result = {'statusCode': res.statusCode};
  } else {
    final decoded = jsonDecode(resBody);
    result = {
      'statusCode': res.statusCode,
      ...(decoded is Map<String, dynamic> ? decoded : {'body': decoded}),
    };
  }
  _logRes(res.statusCode, result, sw.elapsed);
  return result;
}

// ══════════════════════════════════════════════════════════════
// Lambda + S3 업로드 파이프라인
// ══════════════════════════════════════════════════════════════

/// 이미지 파일 경로 → Lambda 서명 URL 발급 → S3 PUT → s3Key 반환
/// 실패 시 null (이미지 없이 계속 진행 가능)
Future<String?> _uploadImageViaLambda(
  String imagePath, {
  int provisionalItemId = 0,
}) async {
  final file = File(imagePath);
  if (!await file.exists()) {
    _log('  ⚠️  이미지 파일을 찾을 수 없음: $imagePath');
    return null;
  }

  final filename = file.uri.pathSegments.last;
  final ext = filename.split('.').last.toLowerCase();
  final contentType = switch (ext) {
    'png' => 'image/png',
    'gif' => 'image/gif',
    'webp' => 'image/webp',
    _ => 'image/jpeg',
  };
  final fileSizeKb = (await file.length()) ~/ 1024;
  _log('  📁 이미지 파일: $filename  ($fileSizeKb KB, $contentType)');

  // ── A. Lambda → presigned URL 발급 ───────────────────────
  _logSection('STEP A · Lambda presigned URL 발급');
  _log('  Lambda URL: $lambdaUrl');
  _log('  요청: itemId=$provisionalItemId  filename=$filename  contentType=$contentType');
  _log('  ※ itemId=$provisionalItemId 은 S3 경로용 임시 값 (등록 전이므로 실제 DB ID 미확보)');

  final lambdaRes = await _lambdaRequest({
    'itemId': provisionalItemId,
    'filename': filename,
    'contentType': contentType,
  });

  if (lambdaRes['statusCode'] != 200) {
    _log('  ❌ Lambda 호출 실패 (HTTP ${lambdaRes['statusCode']}) — 이미지 없이 진행');
    return null;
  }

  final presignedUrl = lambdaRes['presignedUrl'] as String?;
  final s3Key = lambdaRes['s3Key'] as String?;
  final expiresIn = lambdaRes['expiresIn'] ?? 300;

  if (presignedUrl == null || s3Key == null) {
    _log('  ❌ presignedUrl 또는 s3Key 누락 — 이미지 없이 진행');
    _log('    받은 응답: $lambdaRes');
    return null;
  }

  _log('  ✅ presigned URL 수령');
  _log('    s3Key     : $s3Key');
  _log('    expiresIn : ${expiresIn}s');

  // ── B. S3 직접 PUT 업로드 ────────────────────────────────
  _logSection('STEP B · S3 직접 PUT 업로드');
  final imageBytes = await file.readAsBytes();
  final s3Status = await _s3PutUpload(presignedUrl, imageBytes, contentType);

  if (s3Status >= 200 && s3Status < 300) {
    _log('  ✅ S3 업로드 성공');
    _log('    이후 백그라운드 태깅에서 Rekognition이 이 s3Key를 참조합니다');
    return s3Key;
  } else {
    _log('  ❌ S3 업로드 실패 (HTTP $s3Status) — 이미지 없이 진행');
    return null;
  }
}

// ══════════════════════════════════════════════════════════════
// AI 태그 폴링
// ══════════════════════════════════════════════════════════════

Future<void> _pollTagsUntilDone(int itemId, {int maxWaitSec = 90}) async {
  _logSection('STEP · AI 태그 완료 대기 (폴링, 최대 ${maxWaitSec}s)');
  _log('  item_id=$itemId  간격=3초  태깅 파이프라인: Rekognition → CLIP → Gemini');

  final deadline = DateTime.now().add(Duration(seconds: maxWaitSec));
  int attempt = 0;

  while (DateTime.now().isBefore(deadline)) {
    attempt++;
    _log('\n  [폴링 #$attempt]  GET /api/items/$itemId/tags');

    final res = await _jsonRequest('GET', '/api/items/$itemId/tags', auth: true);
    // 라우터에 따라 data 래퍼가 있을 수도 없을 수도 있음 — 양쪽 다 확인
    final data = res['data'] as Map<String, dynamic>? ?? res;
    final hasVector = data['hasVector'] ?? false;
    final category = data['category'] ?? '-';
    final features = (data['features'] as List?)?.cast<String>() ?? [];
    final imageUrl = data['imageUrl'] ?? '-';

    _log('    category : $category');
    _log('    features : ${features.isEmpty ? "(없음)" : features.join(", ")}');
    _log('    hasVector: $hasVector  ← CLIP 임베딩 완료 여부');
    _log('    imageUrl : $imageUrl');

    if (hasVector == true) {
      _log('  ✅ 태깅 파이프라인 완료! (Rekognition + CLIP + Gemini 모두 종료)');
      return;
    }
    if (res['statusCode'] != 200) {
      _log('  ⚠️  API 오류 (HTTP ${res['statusCode']}) — 폴링 중단');
      return;
    }

    final remaining = deadline.difference(DateTime.now()).inSeconds;
    _log('  ⏳ 태깅 진행 중... 3초 후 재시도 (남은 시간: ${remaining}s)');
    await Future.delayed(const Duration(seconds: 3));
  }

  _log('  ⚠️  최대 대기 시간(${maxWaitSec}s) 초과');
  _log('     서버 로그에서 "태깅 완료" 또는 "태깅 실패" 메시지를 확인하세요');
}

// ── 공통 헬퍼 ─────────────────────────────────────────────────
void _printStep(String title) {
  print('\n${'═' * 60}');
  print('  $title');
  print('${'═' * 60}');
}

void _ask(String msg) => stdout.write('\n▶ $msg');
String _read() => stdin.readLineSync(encoding: utf8) ?? '';

// ══════════════════════════════════════════════════════════════
// STEP 0 · 헬스체크
// ══════════════════════════════════════════════════════════════
Future<void> stepHealth() async {
  _printStep('STEP 0 · 헬스체크');
  await _jsonRequest('GET', '/health');
}

// ══════════════════════════════════════════════════════════════
// STEP 1 · 회원가입
// ══════════════════════════════════════════════════════════════
Future<void> stepSignup() async {
  _printStep('STEP 1 · 회원가입');
  _ask('email: ');
  final email = _read();
  _ask('password (8자+): ');
  final password = _read();
  _ask('username: ');
  final username = _read();

  final res = await _jsonRequest('POST', '/api/auth/signup', body: {
    'email': email,
    'password': password,
    'username': username,
  });
  if (res['statusCode'] == 201) {
    _accessToken = res['data']?['accessToken'];
    _log('🔑 토큰 저장 완료');
  }
}

// ══════════════════════════════════════════════════════════════
// STEP 2 · 로그인
// ══════════════════════════════════════════════════════════════
Future<void> stepSignin() async {
  _printStep('STEP 2 · 로그인');
  _ask('email: ');
  final email = _read();
  _ask('password: ');
  final password = _read();

  final res = await _jsonRequest('POST', '/api/auth/signin', body: {
    'email': email,
    'password': password,
  });
  if (res['statusCode'] == 200) {
    _accessToken = res['data']?['accessToken'] ?? res['accessToken'];
    _log('🔑 토큰 저장 완료');
  }
}

// ══════════════════════════════════════════════════════════════
// STEP 3 · 내 정보 조회
// ══════════════════════════════════════════════════════════════
Future<void> stepGetMe() async {
  _printStep('STEP 3 · 내 정보 조회');
  await _jsonRequest('GET', '/api/users/me', auth: true);
}

// ══════════════════════════════════════════════════════════════
// STEP 4 · 분실물 등록 (Lambda → S3 → 등록 → 태그 폴링)
// ══════════════════════════════════════════════════════════════
Future<void> stepCreateLostItem() async {
  _printStep('STEP 4 · 분실물 등록  [Lambda → S3 → 등록 → 태그 폴링]');
  _ask('물건 이름 (예: 에어팟): ');
  final itemName = _read();
  _ask('location (예: 중앙도서관 3층): ');
  final location = _read();
  _ask('raw_text (상세 설명, 선택): ');
  final rawText = _read();
  final defaultImage = Platform.script.resolve('wallet.jpg').toFilePath();
  _ask('이미지 경로 (엔터 → $defaultImage): ');
  final imageInput = _read();
  final imagePath = imageInput.trim().isEmpty ? defaultImage : imageInput.trim();

  final now = DateTime.now();
  final start = now.subtract(const Duration(days: 3)).toIso8601String();
  final end = now.toIso8601String();

  // ── 이미지 있으면 Lambda → S3 업로드 ─────────────────────
  String? s3Key;
  if (imagePath.isNotEmpty) {
    s3Key = await _uploadImageViaLambda(imagePath);
  } else {
    _log('  ℹ️  이미지 없음 — 텍스트 전용으로 Gemini 태깅 진행');
  }

  // ── 아이템 DB 등록 ────────────────────────────────────────
  _logSection('STEP C · 분실물 DB 등록');
  _log('  s3_key 포함: ${s3Key != null ? "✅ $s3Key" : "❌ 없음 (텍스트 기반 태깅)"}');

  final fields = <String, String>{
    'item_name': itemName,
    'date_start': start,
    'date_end': end,
    'location': location,
    if (rawText.trim().isNotEmpty) 'raw_text': rawText.trim(),
    if (s3Key != null) 's3_key': s3Key,
  };

  final res = await _multipartRequest('/api/items/lost', fields, auth: true);

  if (res['statusCode'] == 201) {
    _lostItemId = res['data']?['item_id'] as int?;
    _log('📌 분실물 ID: $_lostItemId 저장됨');
    _log('  category: ${res['data']?['category']}  (백그라운드 태깅 완료 후 업데이트됨)');
    _log('  백그라운드 순서: Rekognition → CLIP → Gemini → 매칭');

    _ask('AI 태그 완료될 때까지 폴링할까요? (y/n): ');
    if (_read().trim().toLowerCase() == 'y') {
      await _pollTagsUntilDone(_lostItemId!);
    }
  }
}

// ══════════════════════════════════════════════════════════════
// STEP 5 · 습득물 등록 (Lambda → S3 → 등록 → 태그 폴링)
// ══════════════════════════════════════════════════════════════
Future<void> stepCreateFoundItem() async {
  _printStep('STEP 5 · 습득물 등록  [Lambda → S3 → 등록 → 태그 폴링]');
  _ask('물건 이름 (예: 에어팟): ');
  final itemName = _read();
  _ask('location (예: 중앙도서관 로비): ');
  final location = _read();
  _ask('raw_text (선택): ');
  final rawText = _read();
  final defaultImage2 = Platform.script.resolve('wallet.jpg').toFilePath();
  _ask('이미지 경로 (엔터 → $defaultImage2): ');
  final imageInput2 = _read();
  final imagePath = imageInput2.trim().isEmpty ? defaultImage2 : imageInput2.trim();

  String? s3Key;
  if (imagePath.isNotEmpty) {
    s3Key = await _uploadImageViaLambda(imagePath);
  } else {
    _log('  ℹ️  이미지 없음 — 텍스트 전용으로 Gemini 태깅 진행');
  }

  _logSection('STEP C · 습득물 DB 등록');
  _log('  s3_key 포함: ${s3Key != null ? "✅ $s3Key" : "❌ 없음"}');

  final fields = <String, String>{
    'item_name': itemName,
    'found_date': DateTime.now().toIso8601String(),
    'location': location,
    if (rawText.trim().isNotEmpty) 'raw_text': rawText.trim(),
    if (s3Key != null) 's3_key': s3Key,
  };

  final res = await _multipartRequest('/api/items/found', fields, auth: true);

  if (res['statusCode'] == 201) {
    _foundItemId = res['data']?['item_id'] as int?;
    _log('📌 습득물 ID: $_foundItemId 저장됨');
    _log('  category: ${res['data']?['category']}  (백그라운드 태깅 완료 후 업데이트됨)');

    _ask('AI 태그 완료될 때까지 폴링할까요? (y/n): ');
    if (_read().trim().toLowerCase() == 'y') {
      await _pollTagsUntilDone(_foundItemId!);
    }
  }
}

// ══════════════════════════════════════════════════════════════
// STEP 6 · 분실물 단건 조회
// ══════════════════════════════════════════════════════════════
Future<void> stepGetLostItem() async {
  _printStep('STEP 6 · 분실물 단건 조회');
  final id = _lostItemId;
  if (id == null) {
    _log('⚠️  분실물 ID 없음. STEP 4 먼저 실행하세요.');
    return;
  }
  await _jsonRequest('GET', '/api/items/lost/$id', auth: true);
}

// ══════════════════════════════════════════════════════════════
// STEP 7 · AI 태그 단건 조회
// ══════════════════════════════════════════════════════════════
Future<void> stepGetTags() async {
  _printStep('STEP 7 · AI 태그 조회');
  _ask('item_id (엔터 → 분실물 ID $_lostItemId): ');
  final input = _read();
  final id = input.isEmpty ? _lostItemId : int.tryParse(input);
  if (id == null) {
    _log('⚠️  유효한 ID 없음');
    return;
  }
  await _jsonRequest('GET', '/api/items/$id/tags', auth: true);
}

// ══════════════════════════════════════════════════════════════
// STEP 7.5 · AI 태그 완료 대기 (폴링)
// ══════════════════════════════════════════════════════════════
Future<void> stepPollTags() async {
  _printStep('STEP 7.5 · AI 태그 완료 대기 (폴링)');
  _ask('item_id (엔터 → 분실물 ID $_lostItemId): ');
  final input = _read();
  final id = input.isEmpty ? _lostItemId : int.tryParse(input);
  if (id == null) {
    _log('⚠️  유효한 ID 없음');
    return;
  }
  _ask('최대 대기 시간 초 (기본 90): ');
  final secInput = _read().trim();
  final maxSec = int.tryParse(secInput) ?? 90;
  await _pollTagsUntilDone(id, maxWaitSec: maxSec);
}

// ══════════════════════════════════════════════════════════════
// STEP 8 · 매칭 결과 조회
// ══════════════════════════════════════════════════════════════
Future<void> stepGetMatches() async {
  _printStep('STEP 8 · 매칭 결과 조회');
  final id = _lostItemId;
  if (id == null) {
    _log('⚠️  분실물 ID 없음');
    return;
  }
  final res = await _jsonRequest('GET', '/api/items/lost/$id/similarity', auth: true);
  final matches = res['matches'] as List?;
  if (matches != null && matches.isNotEmpty) {
    _matchId = matches.first['id'] as int?;
    _log('📌 첫 번째 매칭 ID: $_matchId 저장됨');
  }
}

// ══════════════════════════════════════════════════════════════
// STEP 9 · 매칭 확정
// ══════════════════════════════════════════════════════════════
Future<void> stepConfirmMatch() async {
  _printStep('STEP 9 · 매칭 확정');
  final id = _matchId;
  if (id == null) {
    _log('⚠️  매칭 ID 없음. STEP 8 먼저 실행하세요.');
    return;
  }
  await _jsonRequest(
    'PATCH',
    '/api/matches/$id/confirm',
    auth: true,
    body: {'is_confirmed': true},
  );
}

// ══════════════════════════════════════════════════════════════
// STEP 10 · 내 아이템/매칭 목록
// ══════════════════════════════════════════════════════════════
Future<void> stepGetMyItems() async {
  _printStep('STEP 10 · 내 분실물 / 습득물 / 매칭 목록');
  _log('--- 내 분실물 ---');
  await _jsonRequest('GET', '/api/users/me/lost-items', auth: true);
  _log('\n--- 내 습득물 ---');
  await _jsonRequest('GET', '/api/users/me/found-items', auth: true);
  _log('\n--- 내 매칭 목록 ---');
  await _jsonRequest('GET', '/api/users/me/matches', auth: true);
}

// ══════════════════════════════════════════════════════════════
// STEP 11 · 로그아웃
// ══════════════════════════════════════════════════════════════
Future<void> stepLogout() async {
  _printStep('STEP 11 · 로그아웃');
  final res = await _jsonRequest('DELETE', '/api/auth/logout', auth: true);
  if (res['statusCode'] == 200) {
    _accessToken = null;
    _log('🔑 토큰 삭제 완료');
  }
}

// ══════════════════════════════════════════════════════════════
// 전체 플로우 자동 실행 (99)
// ══════════════════════════════════════════════════════════════
Future<void> runFullFlow() async {
  _log('🚀 전체 플로우 자동 실행 시작');
  await stepHealth();
  await stepSignup();
  await stepGetMe();
  await stepCreateLostItem();
  await stepCreateFoundItem();
  await stepGetLostItem();
  await stepGetTags();
  await stepGetMatches();
  await stepConfirmMatch();
  await stepGetMyItems();
  await stepLogout();
  _log('✅ 전체 플로우 완료');
}

// ══════════════════════════════════════════════════════════════
// 메인 메뉴
// ══════════════════════════════════════════════════════════════
void _printMenu() {
  print('''

╔══════════════════════════════════════════════════════╗
║            Chatda Backend Mock Client                ║
║  Server : $baseUrl
║  Lambda : $lambdaUrl
╠══════════════════════════════════════════════════════╣
║  0     헬스체크                                      ║
║  1     회원가입                                      ║
║  2     로그인                                        ║
║  3     내 정보 조회                                  ║
║  4     분실물 등록 (Lambda→S3→등록→태그폴링)         ║
║  5     습득물 등록 (Lambda→S3→등록→태그폴링)         ║
║  6     분실물 단건 조회                              ║
║  7     AI 태그 단건 조회                             ║
║  7.5   AI 태그 완료 대기 (폴링)                     ║
║  8     매칭 결과 조회                                ║
║  9     매칭 확정                                     ║
║  10    내 아이템/매칭 목록                           ║
║  11    로그아웃                                      ║
║  99    전체 플로우 자동 실행                         ║
║  q     종료                                          ║
╚══════════════════════════════════════════════════════╝''');
  print(
    '  🔑 토큰: ${_accessToken != null ? "있음" : "없음"}'
    '  📌 분실물: $_lostItemId'
    '  📌 습득물: $_foundItemId'
    '  📌 매칭: $_matchId',
  );
}

Future<void> main() async {
  while (true) {
    _printMenu();
    _ask('메뉴 선택: ');
    final input = _read().trim();

    switch (input) {
      case '0':
        await stepHealth();
        break;
      case '1':
        await stepSignup();
        break;
      case '2':
        await stepSignin();
        break;
      case '3':
        await stepGetMe();
        break;
      case '4':
        await stepCreateLostItem();
        break;
      case '5':
        await stepCreateFoundItem();
        break;
      case '6':
        await stepGetLostItem();
        break;
      case '7':
        await stepGetTags();
        break;
      case '7.5':
        await stepPollTags();
        break;
      case '8':
        await stepGetMatches();
        break;
      case '9':
        await stepConfirmMatch();
        break;
      case '10':
        await stepGetMyItems();
        break;
      case '11':
        await stepLogout();
        break;
      case '99':
        await runFullFlow();
        break;
      case 'q':
        _log('👋 종료합니다.');
        exit(0);
      default:
        _log('⚠️  잘못된 입력: "$input"');
    }
  }
}
