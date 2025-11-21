# Ansible

### Inventory

>*ref: https://docs.ansible.com/projects/ansible/latest/inventory_guide/intro_inventory.html*

- An inventory file is used to define different nodes (servers) in the cluster.
- An inventory file can be in `INI` or `YAML` format.

    ```yaml
    # https://stackoverflow.com/questions/50788277/why-3-dashes-hyphen-in-yaml-file
    ---
    k3s_cluster:
    children:
        server:
        hosts:
            52.10.157.197:
        agent:
        hosts:
            35.89.255.141:
            54.185.202.134:

    # Required Vars
    vars:
        ansible_user: ec2-user
        ansible_ssh_private_key_file: ../aws/ssh-key/private-key.pem
        ansible_python_interpreter: /usr/bin/python3
    ```

    One top-level group: k3s_cluster. Under it, two child groups: server and agent. Each child group has hosts by IP. vars apply to the whole k3s_cluster (so all those hosts)

- Doing a ping test to verify connectivity to all nodes:
    ```shell
    uvx --from ansible-core ansible -i inventory.yaml k3s_cluster -m ping

    54.185.202.134 | SUCCESS => {
        "changed": false,
        "ping": "pong"
    }
    52.10.157.197 | SUCCESS => {
        "changed": false,
        "ping": "pong"
    }
    35.89.255.141 | SUCCESS => {
        "changed": false,
        "ping": "pong"
    }
    ```

- To ping a specific group:
    ```shell
    # To ping the server node:
    uvx --from ansible-core ansible -i inventory.yaml server -m ping

    # To ping the agent nodes:
    uvx --from ansible-core ansible -i inventory.yaml agent -m ping
    ```

- To list all hosts in the inventory:
    ```shell
    uvx --from ansible-core ansible-inventory -i inventory.yaml --list

    {
        "_meta": {
            "hostvars": {
                "35.89.255.141": {
                    "ansible_python_interpreter": "/usr/bin/python3",
                    "ansible_ssh_private_key_file": "../aws/ssh-key/private-key.pem",
                    "ansible_user": "ec2-user"
                },
                "52.10.157.197": {
                    "ansible_python_interpreter": "/usr/bin/python3",
                    "ansible_ssh_private_key_file": "../aws/ssh-key/private-key.pem",
                    "ansible_user": "ec2-user"
                },
                "54.185.202.134": {
                    "ansible_python_interpreter": "/usr/bin/python3",
                    "ansible_ssh_private_key_file": "../aws/ssh-key/private-key.pem",
                    "ansible_user": "ec2-user"
                }
            },
            "profile": "inventory_legacy"
        },
        "agent": {
            "hosts": [
                "35.89.255.141",
                "54.185.202.134"
            ]
        },
        "all": {
            "children": [
                "ungrouped",
                "k3s_cluster"
            ]
        },
        "k3s_cluster": {
            "children": [
                "server",
                "agent"
            ]
        },
        "server": {
            "hosts": [
                "52.10.157.197"
            ]
        }
    }
    ```


### Ansible Config

> ref: https://docs.ansible.com/projects/ansible/latest/installation_guide/intro_configuration.html

The Ansible configuration file, typically named `ansible.cfg`, is used to control the default behavior of Ansible. It allows for customization of various settings, such as inventory location, remote user, connection type, privilege escalation, and more.

```ini
[defaults]
inventory = ./inventory.yaml ; specify the inventory file location
host_key_checking = False ; disable host key checking for SSH
retry_files_enabled = False ; disable creation of retry files
interpreter_python = auto_silent ; automatically detect Python interpreter without warnings
```

By defining, a config file like this, you can simply run:
```shell
uvx --from ansible-core ansible k3s_cluster -m ping
```

A [reference](https://gist.github.com/wbcurry/f38bc6d8d1ee4a70ee2c) config file.

### Playbooks

> refs:
> - https://docs.ansible.com/projects/ansible/latest/getting_started/get_started_playbook.html
> - https://docs.ansible.com/projects/ansible/latest/playbook_guide/playbooks_intro.html

Playbooks are automation blueprints, in YAML format, that Ansible uses to deploy and configure managed nodes.

- Playbook - A list of plays that define the order in which Ansible performs operations, from top to bottom, to achieve an overall goal.

- Play - An ordered list of tasks that maps to managed nodes in an inventory.

- Task - A reference to a single module that defines the operations that Ansible performs.

- Module - A unit of code or binary that Ansible runs on managed nodes. Ansible modules are grouped in collections with a Fully Qualified Collection Name (FQCN) for each module.

```shell
# To run a playbook:
uvx --from ansible-core ansible-playbook playbooks/ping-hosts.yaml
```


## Automating K3s Cluster Setup with Ansible

- [ ] Create the inventory file dynamically, when the CDK provisions the EC2 instances.
- [ ] Write Ansible playbooks to:
  - [ ] Install K3s on the server using `curl -sfL https://get.k3s.io | sh -`
  - [ ] Check if K3s server is up and running.
  - [ ] Retrieve the node-token from the server. The value to use for K3S_TOKEN is stored at `/var/lib/rancher/k3s/server/node-token` on your server node.
  - [ ] Install K3s on the agents using the node-token and server IP, `curl -sfL https://get.k3s.io | K3S_URL=https://{server-public-ip}:6443 K3S_TOKEN=nodetoken sh -`
  - [ ] Verify that the agent is running on the agent nodes.
  - [ ] On the server node, verify that all nodes (server + agents) are part of the K3s cluster using `sudo k3s kubectl get nodes`.
  - [ ] Retrieve the K3s kubeconfig file from the server to the local machine for kubectl access.
  - [ ] Replace the localhost(127.0.0.1) in the kubeconfig file with the server's IP address.
  - [ ] Merge the K3s kubeconfig with existing kubeconfig files, if any.

* We do not want to manually hardcode server/agent IPs anywhere, except in the Ansible inventory file.
* The node-token should not be hardcoded anywhere.


