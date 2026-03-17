#!/bin/bash
# Redline Service — Sample API Requests
# Assumes the service is running at http://localhost:8000

BASE="http://localhost:8000/api"

echo "=== Create Document ==="
DOC=$(curl -s -X POST "$BASE/documents" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Contract", "content": "This agreement is between Party A and Party B. Party A shall deliver the goods to Party B within 30 days."}')
echo "$DOC" | python3 -m json.tool
DOC_ID=$(echo "$DOC" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

echo -e "\n=== List Documents ==="
curl -s "$BASE/documents" | python3 -m json.tool

echo -e "\n=== Get Document ==="
curl -s "$BASE/documents/$DOC_ID" | python3 -m json.tool

echo -e "\n=== Patch Document (single change) ==="
curl -s -X PATCH "$BASE/documents/$DOC_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "changes": [
      {"operation": "replace", "target": {"text": "30 days"}, "replacement": "15 business days"}
    ]
  }' | python3 -m json.tool

echo -e "\n=== Patch Document (bulk changes) ==="
curl -s -X PATCH "$BASE/documents/$DOC_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "changes": [
      {"operation": "replace", "target": {"text": "Party A"}, "replacement": "Seller"},
      {"operation": "replace", "target": {"text": "Party B"}, "replacement": "Buyer"}
    ]
  }' | python3 -m json.tool

echo -e "\n=== Search Documents ==="
curl -s "$BASE/documents/search?q=agreement&limit=5" | python3 -m json.tool

echo -e "\n=== Get Change History ==="
curl -s "$BASE/documents/$DOC_ID/history" | python3 -m json.tool

echo -e "\n=== Search Within Document ==="
curl -s "$BASE/documents/$DOC_ID/search?q=Seller" | python3 -m json.tool
