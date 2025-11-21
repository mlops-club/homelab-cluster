## Setting up K3s Cluster on EC2 Instances with Ansible

This is a single server and two agent K3s cluster setup on AWS EC2 instances using Ansible for automation.

```shell
# Run the full setup:
cd k3s-ansible/
uvx --from ansible-core ansible-playbook playbooks/site.yaml
```