import boto3
from app.config import AWS_REGION, AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME


def detect_labels(s3_key: str, max_labels: int = 10) -> list[str]:
    client = boto3.client(
        "rekognition",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )
    response = client.detect_labels(
        Image={"S3Object": {"Bucket": S3_BUCKET_NAME, "Name": s3_key}},
        MaxLabels=max_labels,
        MinConfidence=70.0,
    )
    return [label["Name"] for label in response["Labels"]]
