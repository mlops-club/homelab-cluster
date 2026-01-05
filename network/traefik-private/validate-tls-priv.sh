#!/bin/bash -euo pipefail

echo "=== Validating TLS Configuration for Private Traefik ==="
echo ""

# Check TLS secrets
echo "1. Checking wildcard TLS secret (priv-wildcard-tls)..."
kubectl get secret priv-wildcard-tls -n traefik-private -o jsonpath='{.type}' 2>/dev/null | grep -q "kubernetes.io/tls" \
  && echo "   ✓ Secret exists in traefik-private and is type kubernetes.io/tls" \
  || echo "   ✗ Secret missing or wrong type in traefik-private"
echo ""

# Check Traefik service ports
echo "2. Checking Traefik service ports..."
kubectl get svc traefik-private -n traefik-private -o jsonpath='{.spec.ports[*].port}' | grep -q "80" && echo "   ✓ HTTP port (80) configured" || echo "   ✗ HTTP port missing"
kubectl get svc traefik-private -n traefik-private -o jsonpath='{.spec.ports[*].port}' | grep -q "443" && echo "   ✓ HTTPS port (443) configured" || echo "   ✗ HTTPS port missing"
echo ""

# Check Traefik pods
echo "3. Checking Traefik pods..."
kubectl get pods -n traefik-private -l app.kubernetes.io/name=traefik | grep -q Running && echo "   ✓ Traefik pods running" || echo "   ✗ Traefik pods not running"
echo ""

# Check Ingress TLS configuration
echo "4. Checking Ingress entrypoints..."
ENTRYPOINTS=$(kubectl get ingress whoami -n whoami-priv -o jsonpath='{.metadata.annotations.traefik\.ingress\.kubernetes\.io/router\.entrypoints}' 2>/dev/null)
if echo "$ENTRYPOINTS" | grep -q "websecure"; then
  echo "   ✓ websecure entrypoint configured"
else
  echo "   ✗ websecure entrypoint missing"
fi
echo ""

# Test HTTP redirect
echo "5. Testing HTTP to HTTPS redirect..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://whoami.priv.mlops-club.org 2>/dev/null || echo "000")
if [ "$HTTP_STATUS" = "301" ] || [ "$HTTP_STATUS" = "308" ]; then
  echo "   ✓ HTTP redirects to HTTPS (status: $HTTP_STATUS)"
else
  echo "   ✗ HTTP redirect not working (status: $HTTP_STATUS)"
fi
echo ""

# Test HTTPS access
echo "6. Testing HTTPS access..."
HTTPS_STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" https://whoami.priv.mlops-club.org 2>/dev/null || echo "000")
if [ "$HTTPS_STATUS" = "200" ]; then
  echo "   ✓ HTTPS access working (status: $HTTPS_STATUS)"
else
  echo "   ✗ HTTPS access not working (status: $HTTPS_STATUS)"
fi
echo ""

# Check certificate
echo "7. Checking TLS certificate..."
CERT_INFO=$(echo | openssl s_client -connect whoami.priv.mlops-club.org:443 -servername whoami.priv.mlops-club.org 2>/dev/null | openssl x509 -noout -subject 2>/dev/null || echo "")
if [ -n "$CERT_INFO" ]; then
  echo "   ✓ Certificate found: $CERT_INFO"
else
  echo "   ✗ Could not retrieve certificate"
fi
echo ""

echo "=== Validation Complete ==="

