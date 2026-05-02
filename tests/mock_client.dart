import 'dart:convert';
import 'dart:io';
import 'dart:math';

// ── 설정 ──────────────────────────────────────────────────
const String baseUrl = 'http://127.0.0.1:8000';

// ── 전역 상태 ─────────────────────────────────────────────
String? _accessToken;
int? _lostItemId;
int? _foundItemId;
int? _matchId;

// ══════════════════════════════════════════════════════════
// HTTP 헬퍼
// ══════════════════════════════════════════════════════════

/// JSON 요청 (auth, items 조회/수정/삭제 등)
Future<Map<String, dynamic>> _jsonRequest(
  String method,
  String path, {
  Map<String, dynamic>? body,
  bool auth = false,
}) async {
  final client = HttpClient();
  final uri = Uri.parse('$baseUrl$path');

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

  if (resBody.isEmpty) return {'statusCode': res.statusCode};
  final decoded = jsonDecode(resBody);
  return {
    'statusCode': res.statusCode,
    ...?(decoded is Map<String, dynamic> ? decoded : {'body': decoded}),
  };
}

/// multipart/form-data 요청 (분실물/습득물 등록 - 이미지 포함)
Future<Map<String, dynamic>> _multipartRequest(
  String path,
  Map<String, String> fields, {
  String? imagePath,
  bool auth = false,
}) async {
  final boundary = '----DartBoundary${Random().nextInt(999999)}';
  final client = HttpClient();
  final uri = Uri.parse('$baseUrl$path');
  final req = await client.postUrl(uri);

  req.headers.set('Content-Type', 'multipart/form-data; boundary=$boundary');
  if (auth && _accessToken != null) {
    req.headers.set('Authorization', 'Bearer $_accessToken');
  }

  final bodyBytes = <int>[];

  // 텍스트 필드
  fields.forEach((key, value) {
    bodyBytes.addAll(utf8.encode('--$boundary\r\n'));
    bodyBytes.addAll(
      utf8.encode('Content-Disposition: form-data; name="$key"\r\n'),
    );
    bodyBytes.addAll(
      utf8.encode('Content-Type: text/plain; charset=utf-8\r\n\r\n'),
    );
    bodyBytes.addAll(utf8.encode(value));
    bodyBytes.addAll(utf8.encode('\r\n'));
  });

  // 이미지 파일 (선택)
  if (imagePath != null) {
    final file = File(imagePath);
    if (await file.exists()) {
      final fileName = file.uri.pathSegments.last;
      final fileBytes = await file.readAsBytes();
      bodyBytes.addAll(utf8.encode('--$boundary\r\n'));
      bodyBytes.addAll(
        utf8.encode(
          'Content-Disposition: form-data; name="image"; filename="$fileName"\r\n'
          'Content-Type: image/jpeg\r\n\r\n',
        ),
      );
      bodyBytes.addAll(fileBytes);
      bodyBytes.addAll(utf8.encode('\r\n'));
    } else {
      print('⚠️  이미지 파일 없음: $imagePath (텍스트만 전송)');
    }
  }

  bodyBytes.addAll(utf8.encode('--$boundary--\r\n'));

  req.headers.contentLength = bodyBytes.length;
  req.add(bodyBytes);

  final res = await req.close();
  final resBody = await res.transform(utf8.decoder).join();
  client.close();

  if (resBody.isEmpty) return {'statusCode': res.statusCode};
  final decoded = jsonDecode(resBody);
  return {
    'statusCode': res.statusCode,
    ...?(decoded is Map<String, dynamic> ? decoded : {'body': decoded}),
  };
}

// ── 출력 헬퍼 ─────────────────────────────────────────────
void _printStep(String title) {
  print('\n${'═' * 55}');
  print('  $title');
  print('${'═' * 55}');
}

void _printResult(Map<String, dynamic> res) {
  final status = res['statusCode'];
  final ok = status != null && status < 300;
  print(ok ? '✅ 성공 [$status]' : '❌ 실패 [$status]');
  print(const JsonEncoder.withIndent('  ').convert(res));
}

void _ask(String msg) => stdout.write('\n▶ $msg');
String _read() => stdin.readLineSync(encoding: utf8) ?? '';

// ══════════════════════════════════════════════════════════
// STEP 0 · 헬스체크
// ══════════════════════════════════════════════════════════
Future<void> stepHealth() async {
  _printStep('STEP 0 · 헬스체크');
  _printResult(await _jsonRequest('GET', '/health'));
}

// ══════════════════════════════════════════════════════════
// STEP 1 · 회원가입
// ══════════════════════════════════════════════════════════
Future<void> stepSignup() async {
  _printStep('STEP 1 · 회원가입');
  _ask('email 입력: ');
  final email = _read();
  _ask('password 입력 (8자 이상): ');
  final password = _read();
  _ask('username(닉네임) 입력: ');
  final username = _read();

  final res = await _jsonRequest(
    'POST',
    '/api/auth/signup',
    body: {'email': email, 'password': password, 'username': username},
  );
  _printResult(res);

  if (res['statusCode'] == 201) {
    _accessToken = res['data']?['accessToken'];
    print('\n🔑 토큰 저장 완료');
  }
}

// ══════════════════════════════════════════════════════════
// STEP 2 · 로그인
// ══════════════════════════════════════════════════════════
Future<void> stepSignin() async {
  _printStep('STEP 2 · 로그인');
  _ask('email 입력: ');
  final email = _read();
  _ask('password 입력: ');
  final password = _read();

  final res = await _jsonRequest(
    'POST',
    '/api/auth/signin',
    body: {'email': email, 'password': password},
  );
  _printResult(res);

  if (res['statusCode'] == 200) {
    _accessToken = res['data']?['accessToken'] ?? res['accessToken'];
    print('\n🔑 토큰 저장 완료');
  }
}

// ══════════════════════════════════════════════════════════
// STEP 3 · 내 정보 조회
// ══════════════════════════════════════════════════════════
Future<void> stepGetMe() async {
  _printStep('STEP 3 · 내 정보 조회');
  _printResult(await _jsonRequest('GET', '/api/users/me', auth: true));
}

// ══════════════════════════════════════════════════════════
// STEP 4 · 분실물 등록
// ══════════════════════════════════════════════════════════
Future<void> stepCreateLostItem() async {
  _printStep('STEP 4 · 분실물 등록');
  _ask('물건 이름 (예: 에어팟): ');
  final itemName = _read();
  _ask('location (예: 중앙도서관 3층): ');
  final location = _read();
  _ask('raw_text (상세 설명, 선택): ');
  final rawText = _read();
  _ask('이미지 경로 (선택, 없으면 엔터): ');
  final imagePath = _read();

  final now = DateTime.now();
  final start = now.subtract(const Duration(days: 3)).toIso8601String();
  final end = now.toIso8601String();

  final res = await _multipartRequest(
    '/api/items/lost',
    {
      'item_name': itemName,
      'date_start': start,
      'date_end': end,
      'location': location,
      if (rawText.isNotEmpty) 'raw_text': rawText,
    },
    imagePath: imagePath.isEmpty ? null : imagePath,
    auth: true,
  );
  _printResult(res);

  if (res['statusCode'] == 201) {
    _lostItemId = res['data']?['item_id'];
    print('\n📌 분실물 ID: $_lostItemId 저장됨');
  }
}

// ══════════════════════════════════════════════════════════
// STEP 5 · 습득물 등록
// ══════════════════════════════════════════════════════════
Future<void> stepCreateFoundItem() async {
  _printStep('STEP 5 · 습득물 등록');
  _ask('물건 이름 (예: 에어팟): ');
  final itemName = _read();
  _ask('location (예: 중앙도서관 로비): ');
  final location = _read();
  _ask('raw_text (상세 설명, 선택): ');
  final rawText = _read();
  _ask('이미지 경로 (선택, 없으면 엔터): ');
  final imagePath = _read();

  final res = await _multipartRequest(
    '/api/items/found',
    {
      'item_name': itemName,
      'found_date': DateTime.now().toIso8601String(),
      'location': location,
      if (rawText.isNotEmpty) 'raw_text': rawText,
    },
    imagePath: imagePath.isEmpty ? null : imagePath,
    auth: true,
  );
  _printResult(res);

  if (res['statusCode'] == 201) {
    _foundItemId = res['data']?['item_id'];
    print('\n📌 습득물 ID: $_foundItemId 저장됨');
  }
}

// ══════════════════════════════════════════════════════════
// STEP 6 · 분실물 단건 조회
// ══════════════════════════════════════════════════════════
Future<void> stepGetLostItem() async {
  _printStep('STEP 6 · 분실물 단건 조회');
  final id = _lostItemId;
  if (id == null) {
    print('⚠️  분실물 ID 없음. STEP 4 먼저 실행하세요.');
    return;
  }
  _printResult(await _jsonRequest('GET', '/api/items/lost/$id', auth: true));
}

// ══════════════════════════════════════════════════════════
// STEP 7 · AI 태그 조회
// ══════════════════════════════════════════════════════════
Future<void> stepGetTags() async {
  _printStep('STEP 7 · AI 태그 조회');
  _ask('item_id 입력 (엔터 시 분실물 ID 사용: $_lostItemId): ');
  final input = _read();
  final id = input.isEmpty ? _lostItemId : int.tryParse(input);
  if (id == null) {
    print('⚠️  유효한 ID 없음');
    return;
  }
  _printResult(await _jsonRequest('GET', '/api/items/$id/tags', auth: true));
}

// ══════════════════════════════════════════════════════════
// STEP 8 · 매칭 결과 조회
// ══════════════════════════════════════════════════════════
Future<void> stepGetMatches() async {
  _printStep('STEP 8 · 매칭 결과 조회');
  final id = _lostItemId;
  if (id == null) {
    print('⚠️  분실물 ID 없음');
    return;
  }
  final res = await _jsonRequest(
    'GET',
    '/api/items/lost/$id/similarity',
    auth: true,
  );
  _printResult(res);

  final matches = res['matches'] as List?;
  if (matches != null && matches.isNotEmpty) {
    _matchId = matches.first['id'];
    print('\n📌 첫 번째 매칭 ID: $_matchId 저장됨');
  }
}

// ══════════════════════════════════════════════════════════
// STEP 9 · 매칭 확정
// ══════════════════════════════════════════════════════════
Future<void> stepConfirmMatch() async {
  _printStep('STEP 9 · 매칭 확정');
  final id = _matchId;
  if (id == null) {
    print('⚠️  매칭 ID 없음. STEP 8 먼저 실행하세요.');
    return;
  }
  _printResult(
    await _jsonRequest(
      'PATCH',
      '/api/matches/$id/confirm',
      auth: true,
      body: {'is_confirmed': true},
    ),
  );
}

// ══════════════════════════════════════════════════════════
// STEP 10 · 내 아이템/매칭 목록
// ══════════════════════════════════════════════════════════
Future<void> stepGetMyItems() async {
  _printStep('STEP 10 · 내 분실물 / 습득물 / 매칭 목록');
  print('\n--- 내 분실물 ---');
  _printResult(
    await _jsonRequest('GET', '/api/users/me/lost-items', auth: true),
  );
  print('\n--- 내 습득물 ---');
  _printResult(
    await _jsonRequest('GET', '/api/users/me/found-items', auth: true),
  );
  print('\n--- 내 매칭 목록 ---');
  _printResult(await _jsonRequest('GET', '/api/users/me/matches', auth: true));
}

// ══════════════════════════════════════════════════════════
// STEP 11 · 로그아웃
// ══════════════════════════════════════════════════════════
Future<void> stepLogout() async {
  _printStep('STEP 11 · 로그아웃');
  final res = await _jsonRequest('DELETE', '/api/auth/logout', auth: true);
  _printResult(res);
  if (res['statusCode'] == 200) {
    _accessToken = null;
    print('\n🔑 토큰 삭제 완료');
  }
}

// ══════════════════════════════════════════════════════════
// 전체 플로우 자동 실행 (99)
// ══════════════════════════════════════════════════════════
Future<void> runFullFlow() async {
  print('\n🚀 전체 플로우 자동 실행');
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
  print('\n✅ 전체 플로우 완료');
}

// ══════════════════════════════════════════════════════════
// 메인 메뉴
// ══════════════════════════════════════════════════════════
void _printMenu() {
  print('''

╔═══════════════════════════════════════════╗
║       Chatda Backend Mock Client          ║
║       Server: $baseUrl
╠═══════════════════════════════════════════╣
║  0   헬스체크                             ║
║  1   회원가입                             ║
║  2   로그인                               ║
║  3   내 정보 조회                         ║
║  4   분실물 등록 (item_name + multipart)  ║
║  5   습득물 등록 (item_name + multipart)  ║
║  6   분실물 단건 조회                     ║
║  7   AI 태그 조회                         ║
║  8   매칭 결과 조회                       ║
║  9   매칭 확정                            ║
║  10  내 아이템/매칭 목록                  ║
║  11  로그아웃                             ║
║  99  전체 플로우 자동 실행                ║
║  q   종료                                 ║
╚═══════════════════════════════════════════╝''');
  print(
    '🔑 토큰: ${_accessToken != null ? "있음" : "없음"}'
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
        print('\n👋 종료합니다.');
        exit(0);
      default:
        print('⚠️  잘못된 입력입니다.');
    }
  }
}
