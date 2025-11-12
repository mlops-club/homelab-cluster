After installing K3s on the EC2 instance:

- I ran `sudo systemctl status k3s` to check the status of the K3s service.
```shell
[ec2-user@ip-10-51-67-194 ~]$ sudo systemctl status k3s
● k3s.service - Lightweight Kubernetes
     Loaded: loaded (/etc/systemd/system/k3s.service; enabled; preset: disabled)
     Active: active (running) since Tue 2025-11-11 06:37:50 UTC; 20min ago
       Docs: https://k3s.io
    Process: 8305 ExecStartPre=/sbin/modprobe br_netfilter (code=exited, status=0/SUCCESS)
    Process: 8392 ExecStartPre=/sbin/modprobe overlay (code=exited, status=0/SUCCESS)
   Main PID: 8413 (k3s-server)
      Tasks: 89
     Memory: 1.5G
        CPU: 1min 57.763s
     CGroup: /system.slice/k3s.service
             ├─ 8413 "/usr/local/bin/k3s server"
             ├─18831 "containerd "
             ├─29083 /var/lib/rancher/k3s/data/86a616cdaf0fb57fa13670ac5a16f1699f4b2be4772e842d97904c69698ffdc2/bin/containerd-shim-runc-v2 -namespace >
             ├─29163 /var/lib/rancher/k3s/data/86a616cdaf0fb57fa13670ac5a16f1699f4b2be4772e842d97904c69698ffdc2/bin/containerd-shim-runc-v2 -namespace >
             ├─29174 /var/lib/rancher/k3s/data/86a616cdaf0fb57fa13670ac5a16f1699f4b2be4772e842d97904c69698ffdc2/bin/containerd-shim-runc-v2 -namespace >
             ├─30224 /var/lib/rancher/k3s/data/86a616cdaf0fb57fa13670ac5a16f1699f4b2be4772e842d97904c69698ffdc2/bin/containerd-shim-runc-v2 -namespace >
             └─30327 /var/lib/rancher/k3s/data/86a616cdaf0fb57fa13670ac5a16f1699f4b2be4772e842d97904c69698ffdc2/bin/containerd-shim-runc-v2 -namespace >

Nov 11 06:38:32 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: I1111 06:38:32.440899    8413 event.go:389] "Event occurred" object="kube-system/>
Nov 11 06:38:35 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: I1111 06:38:35.415397    8413 pod_startup_latency_tracker.go:104] "Observed pod s>
Nov 11 06:38:35 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: I1111 06:38:35.415526    8413 pod_startup_latency_tracker.go:104] "Observed pod s>
Nov 11 06:38:35 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: I1111 06:38:35.456073    8413 event.go:389] "Event occurred" object="kube-system/>
Nov 11 06:38:36 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: I1111 06:38:36.435774    8413 event.go:389] "Event occurred" object="kube-system/>
Nov 11 06:47:47 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: I1111 06:47:47.557803    8413 cidrallocator.go:277] updated ClusterIP allocator f>
Nov 11 06:57:46 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: time="2025-11-11T06:57:46Z" level=info msg="COMPACT compactRev=0 targetCompactRev>
Nov 11 06:57:46 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: time="2025-11-11T06:57:46Z" level=info msg="COMPACT deleted 18 rows from 84 revis>
Nov 11 06:57:46 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: time="2025-11-11T06:57:46Z" level=info msg="COMPACT compacted from 0 to 84 in 1 t>
Nov 11 06:57:47 ip-10-51-67-194.us-west-2.compute.internal k3s[8413]: I1111 06:57:47.558467    8413 cidrallocator.go:277] updated ClusterIP allocator f>
```

- To see if the agent service is running, I ran `sudo systemctl status k3s-agent`:
```shell
[ec2-user@ip-10-51-67-194 ~]$ sudo systemctl status k3s-agent
Unit k3s-agent.service could not be found.
```
^^^ After intalling K3s with `curl -sfL https://get.k3s.io | sh -`, the node is only configured as a server

- To see the nodes in the cluster, I ran `sudo k3s kubectl get nodes`:
```shell
[ec2-user@ip-10-51-67-194 ~]$ sudo k3s kubectl get nodes
NAME                                         STATUS   ROLES                  AGE   VERSION
ip-10-51-67-194.us-west-2.compute.internal   Ready    control-plane,master   21m   v1.33.5+k3s1
```

- I ran this command to see if the K3s server is listening on the default Kubernetes API server port (6443):
```shell
[ec2-user@ip-10-51-67-194 ~]$ sudo netstat -tulpn | grep 6443
tcp6       0      0 :::6443                 :::*                    LISTEN      8413/k3s server 
```

- After running the agent install script on the same node on which the server is installed:
```shell
# nodetoken found at `sudo cat /var/lib/rancher/k3s/server/node-token`
curl -sfL https://get.k3s.io | K3S_URL=https://localhost:6443 K3S_TOKEN=mynodetoken sh -
```

I can see the status of k3s-agent service:
```shell
[ec2-user@ip-10-51-67-194 ~]$ sudo systemctl status k3s-agent
● k3s-agent.service - Lightweight Kubernetes
     Loaded: loaded (/etc/systemd/system/k3s-agent.service; enabled; preset: disabled)
     Active: activating (auto-restart) (Result: exit-code) since Tue 2025-11-11 09:55:19 UTC; 2s ago
       Docs: https://k3s.io
    Process: 44917 ExecStartPre=/sbin/modprobe br_netfilter (code=exited, status=0/SUCCESS)
    Process: 44918 ExecStartPre=/sbin/modprobe overlay (code=exited, status=0/SUCCESS)
    Process: 44919 ExecStart=/usr/local/bin/k3s agent (code=exited, status=1/FAILURE)
   Main PID: 44919 (code=exited, status=1/FAILURE)
        CPU: 163ms
```


sudo cat /var/lib/rancher/k3s/server/node-token
K10a1c4ae0f73fbbbd8af1c6deec19d931c95f135100a76503740f76cf82d4acccc::server:aea12c1184de82bf9a5d9fa8c3a02322


curl -sfL https://get.k3s.io | K3S_URL=https://<server-private-ip>:6443 K3S_TOKEN=<value-from-node-token> sh -


curl -sfL https://get.k3s.io | K3S_URL=https://10.51.67.194:6443 K3S_TOKEN=K10a1c4ae0f73fbbbd8af1c6deec19d931c95f135100a76503740f76cf82d4acccc::server:aea12c1184de82bf9a5d9fa8c3a02322 sh -


curl -skI https://52.41.95.164:6443/livez
curl -skI https://10.51.67.194:6443/livez


openssl s_client -connect 52.41.95.164:6443 -showcerts </dev/null 2>/dev/null \
| openssl x509 -noout -text | grep -A1 "Subject Alternative Name"


scp ec2-user@52.41.95.164:/etc/rancher/k3s/k3s.yaml ~/.kube/k3s-usw2.yaml
scp ec2-user@ec2-52-41-95-164.us-west-2.compute.amazonaws.com:/etc/rancher/k3s/k3s.yaml ~/.kube/k3s-usw2.yaml
chmod 600 ~/.kube/k3s-usw2.yaml


```shell
╭─amitraj@laptop-2 ~/repos/mlops-club/homelab-cluster ‹main●› 
╰─$ scp ec2-user@52.41.95.164:/etc/rancher/k3s/k3s.yaml ~/.kube/k3s-usw2.yaml
ec2-user@52.41.95.164: Permission denied (publickey,gssapi-keyex,gssapi-with-mic).
scp: Connection closed
╭─amitraj@laptop-2 ~/repos/mlops-club/homelab-cluster ‹main●› 
╰─$ scp ec2-user@ec2-52-41-95-164.us-west-2.compute.amazonaws.com:/etc/rancher/k3s/k3s.yaml ~/.kube/k3s-usw2.yaml                                 255 ↵
The authenticity of host 'ec2-52-41-95-164.us-west-2.compute.amazonaws.com (52.41.95.164)' can't be established.
ED25519 key fingerprint is SHA256:I7okvdB7B3HFGwGHvy3eqOH8wTQDzYGtd3v3WQX3Jn8.
This host key is known by the following other names/addresses:
    ~/.ssh/known_hosts:4: 52.41.95.164
Are you sure you want to continue connecting (yes/no/[fingerprint])? yes
Warning: Permanently added 'ec2-52-41-95-164.us-west-2.compute.amazonaws.com' (ED25519) to the list of known hosts.
ec2-user@ec2-52-41-95-164.us-west-2.compute.amazonaws.com: Permission denied (publickey,gssapi-keyex,gssapi-with-mic).
scp: Connection closed
```

This worked:
```shell
ssh -i ./aws/ssh-key/private-key.pem ec2-user@ec2-52-41-95-164.us-west-2.compute.amazonaws.com \
  'sudo cat /etc/rancher/k3s/k3s.yaml' > ~/.kube/k3s-usw2.yaml
chmod 600 ~/.kube/k3s-usw2.yaml
```


To locally run kubectl commands against the K3s cluster:
```shell
# download k3s kubeconfig from the server
ssh -i ./aws/ssh-key/private-key.pem ec2-user@<public-dns> \
  'sudo cat /etc/rancher/k3s/k3s.yaml' > ~/.kube/k3s-usw2.yaml
chmod 600 ~/.kube/k3s-usw2.yaml

# ssh into the server
ssh -NT -L 6443:127.0.0.1:6443 -i ./aws/ssh-key/private-key.pem ec2-user@<public-dns>

# in another terminal, run kubectl commands using the k3s kubeconfig
KUBECONFIG=~/.kube/config kubectl get nodes
KUBECONFIG=~/.kube/config kubectl get pods -n kube-system
```