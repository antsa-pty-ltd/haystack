#!/bin/bash
# Script to add remaining API outbound IPs to haystack service firewall

APP_NAME="antsa-haystack-au-production"
RESOURCE_GROUP="production"

echo "Adding remaining API outbound IPs to haystack service firewall..."

# Remaining IPs that weren't added in the initial setup
REMAINING_IPS=(
    "20.211.58.173"
    "20.211.58.177" 
    "20.211.58.203"
    "20.211.58.249"
    "20.211.59.106"
    "20.211.59.113"
    "20.211.59.114"
    "20.211.59.124"
    "20.211.59.77"
    "20.70.225.102"
    "20.70.228.18"
    "20.70.228.243"
    "20.70.228.70"
    "20.70.231.67"
)

PRIORITY=210

for IP in "${REMAINING_IPS[@]}"; do
    RULE_NAME="API-Extra-${IP//\./-}"
    echo "Adding IP restriction for $IP with priority $PRIORITY"
    
    az webapp config access-restriction add \
        --name "$APP_NAME" \
        --resource-group "$RESOURCE_GROUP" \
        --rule-name "$RULE_NAME" \
        --action Allow \
        --ip-address "$IP/32" \
        --priority $PRIORITY
    
    PRIORITY=$((PRIORITY + 10))
    
    # Small delay to avoid rate limiting
    sleep 1
done

echo "✅ Completed adding remaining IP restrictions"
echo "Run the following command to verify:"
echo "az webapp config access-restriction show --name $APP_NAME --resource-group $RESOURCE_GROUP"