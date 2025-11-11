#!/bin/bash
# Diagnostic script for whoami service access issue

echo "=== Checking whoami pods ==="
k3s kubectl get pods -n default -l app=whoami

echo -e "\n=== Checking whoami service ==="
k3s kubectl get svc -n default whoami -o yaml

echo -e "\n=== Checking whoami ingress ==="
k3s kubectl get ingress -n default whoami -o yaml

echo -e "\n=== Checking Traefik service ports ==="
k3s kubectl get svc -n kube-system | grep traefik

echo -e "\n=== Checking what's listening on port 80 ==="
netstat -tlnp | grep :80 || ss -tlnp | grep :80

echo -e "\n=== Checking what's listening on port 8080 ==="
netstat -tlnp | grep :8080 || ss -tlnp | grep :8080

echo -e "\n=== Testing whoami service endpoint directly ==="
k3s kubectl get svc whoami -n default -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "No LoadBalancer IP assigned"

echo -e "\n=== Testing via service cluster IP ==="
SVC_IP=$(k3s kubectl get svc whoami -n default -o jsonpath='{.spec.clusterIP}')
echo "Service ClusterIP: $SVC_IP"
curl -v http://$SVC_IP:80 2>&1 | head -20

echo -e "\n=== Testing via localhost:80 ==="
curl -v http://localhost:80 2>&1 | head -20

echo -e "\n=== Testing via localhost:8080 ==="
curl -v http://localhost:8080 2>&1 | head -20



