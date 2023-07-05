resource "aws_iam_role" "wbip_wrapper_role" {
  name               = "wbip_wrapper_exec"
  assume_role_policy = file("${path.root}/../../iam/roles/wbip_wrapper_exec.json")
  inline_policy {
    name   = "sort_instapaper_exec"
    policy = file("${path.root}/../../iam/policies/wbip_wrapper_exec.json")
  }
}
