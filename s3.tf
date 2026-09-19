resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "irsa_demo" {
  bucket = "nisha-irsa-demo-${random_id.bucket_suffix.hex}"

  tags = {
    Name = "irsa-demo-bucket"
  }
}

resource "aws_s3_bucket_public_access_block" "irsa_demo" {
  bucket = aws_s3_bucket.irsa_demo.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}