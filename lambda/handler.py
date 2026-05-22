import json
import uuid
import os
import boto3
from botocore.config import Config

REGION = os.environ["AWS_REGION"]
BUCKET = os.environ["S3_BUCKET_NAME"]

# addressing_style="virtual" + signature_version="s3v4" 조합으로
# https://{bucket}.s3.{region}.amazonaws.com/... 형태의 리전 presigned URL 생성
s3 = boto3.client(
    "s3",
    region_name=REGION,
    config=Config(
        signature_version="s3v4",
        s3={"addressing_style": "virtual"},
    ),
)


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        filename = body["filename"]
        content_type = body.get("contentType", "image/jpeg")
    except (KeyError, json.JSONDecodeError) as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": f"잘못된 요청: {e}"}),
        }

    s3_key = f"items/{uuid.uuid4()}_{filename}"

    presigned_url = s3.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": BUCKET,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=300,
    )

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "presignedUrl": presigned_url,
            "s3Key": s3_key,
            "expiresIn": 300,
        }),
    }
