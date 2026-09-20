resource "aws_cloudwatch_event_rule" "guardduty_privesc" {
  name        = "guardduty-rbac-privesc-finding"
  description = "Routes GuardDuty RoleBinding privilege escalation findings to remediation Lambda"

  event_pattern = jsonencode({
    source      = ["aws.guardduty"]
    detail-type = ["GuardDuty Finding"]
    detail = {
      type = ["PrivilegeEscalation:Kubernetes/AnomalousBehavior.RoleBindingCreated"]
    }
  })
}

resource "aws_cloudwatch_event_target" "lambda_remediation" {
  rule      = aws_cloudwatch_event_rule.guardduty_privesc.name
  target_id = "guardduty-remediation-lambda"
  arn       = aws_lambda_function.remediation.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.remediation.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.guardduty_privesc.arn
}