import json
import uuid
import boto3
import os

s3 = boto3.client("s3", region_name=os.environ["AWS_REGION"])
BUCKET = os.environ["S3_BUCKET_NAME"]


def lambda_handler(event, context):
    try:
        body = json.loads(event.get("body", "{}"))
        item_id = body["itemId"]
        filename = body["filename"]
        content_type = body.get("contentType", "image/jpeg")
    except (KeyError, json.JSONDecodeError) as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"message": f"잘못된 요청: {e}"}),
        }

    s3_key = f"items/{item_id}/{uuid.uuid4()}_{filename}"

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
