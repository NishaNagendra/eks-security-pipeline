resource "aws_lambda_function" "remediation" {
  function_name = "guardduty-rbac-remediation"
  role          = aws_iam_role.lambda_remediation.arn
  handler       = "lambda_remediation.lambda_handler"
  runtime       = "python3.13"
  timeout       = 30
  memory_size   = 256

  filename         = "lambda_remediation.zip"
  source_code_hash = filebase64sha256("lambda_remediation.zip")

  vpc_config {
    subnet_ids         = aws_subnet.private[*].id
    security_group_ids = [aws_security_group.lambda_remediation.id]
  }
}