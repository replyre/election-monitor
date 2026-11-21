#!/usr/bin/env bash
# One-off: create the Election Monitor's Azure resources. Safe to re-run; each
# step is a create-or-update. Everything lives in its own resource group.
#
#   SUBSCRIPTION=<id> ./deploy/azure/provision.sh
#
# Prints, at the end, the VM's outbound IP (for the Supabase allowlist) and the
# three ids the GitHub deploy workflow needs.
set -euo pipefail

SUBSCRIPTION="${SUBSCRIPTION:?set SUBSCRIPTION}"
# South India (Chennai) is ~30 ms from the Supabase project in Singapore and
# close to Jharkhand. Southeast Asia would be closer still, but every small size
# there is "NotAvailableForSubscription" for this subscription, and B-series v1
# is blocked in every region; B2als_v2 needed a 2-core quota grant (Basv2).
LOCATION="${LOCATION:-southindia}"
RG="${RG:-giridih-prod}"
VM="${VM:-giridih-vm}"
SIZE="${SIZE:-Standard_B2als_v2}"
REPO="${REPO:-replyre/election-monitor}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/giridih-vm_ed25519}"
HERE="$(cd "$(dirname "$0")" && pwd)"

az account set --subscription "$SUBSCRIPTION"
step() { echo "== $*"; }

step "resource group $RG ($LOCATION)"
az group create -n "$RG" -l "$LOCATION" --tags app=election-monitor -o none

step "network: subnet with a storage service endpoint, NSG denying all inbound"
az network vnet create -g "$RG" -n giridih-vnet --address-prefixes 10.42.0.0/24 \
    --subnet-name app --subnet-prefixes 10.42.0.0/27 -o none
az network nsg create -g "$RG" -n giridih-nsg -o none
az network nsg rule create -g "$RG" --nsg-name giridih-nsg -n deny-all-inbound \
    --priority 100 --direction Inbound --access Deny --protocol '*' \
    --source-address-prefixes '*' --destination-address-prefixes '*' \
    --destination-port-ranges '*' -o none
az network vnet subnet update -g "$RG" --vnet-name giridih-vnet -n app \
    --network-security-group giridih-nsg --service-endpoints Microsoft.Storage -o none

step "static outbound IP (no DNS name; nothing inbound is allowed)"
az network public-ip create -g "$RG" -n giridih-ip --sku Standard \
    --allocation-method Static --version IPv4 --idle-timeout 30 -o none
az network nic create -g "$RG" -n giridih-nic --vnet-name giridih-vnet --subnet app \
    --network-security-group giridih-nsg --public-ip-address giridih-ip -o none

step "VM $VM ($SIZE, Ubuntu 24.04, Trusted Launch)"
[[ -f "$SSH_KEY" ]] || ssh-keygen -t ed25519 -N '' -C giridih-vm -f "$SSH_KEY" >/dev/null
if ! az vm show -g "$RG" -n "$VM" -o none 2>/dev/null; then
    az vm create -g "$RG" -n "$VM" --size "$SIZE" \
        --image Canonical:ubuntu-24_04-lts:server:latest \
        --nics giridih-nic --admin-username azureuser \
        --ssh-key-values "$SSH_KEY.pub" \
        --custom-data "$HERE/cloud-init.yaml" \
        --assign-identity '[system]' \
        --security-type TrustedLaunch --enable-secure-boot true --enable-vtpm true \
        --storage-sku StandardSSD_LRS --os-disk-size-gb 30 \
        --tags app=election-monitor -o none
fi
az vm boot-diagnostics enable -g "$RG" -n "$VM" -o none
VM_ID="$(az vm show -g "$RG" -n "$VM" --query id -o tsv)"
VM_PRINCIPAL="$(az vm show -g "$RG" -n "$VM" --query identity.principalId -o tsv)"

step "backup storage: private, Entra-only, reachable from the VM subnet only"
SA="giridih$(echo -n "$SUBSCRIPTION" | shasum | cut -c1-10)"
az storage account create -g "$RG" -n "$SA" -l "$LOCATION" --sku Standard_LRS --kind StorageV2 \
    --min-tls-version TLS1_2 --https-only true --allow-blob-public-access false \
    --allow-shared-key-access false --default-action Deny -o none
az storage account network-rule add -g "$RG" --account-name "$SA" \
    --vnet-name giridih-vnet --subnet app -o none
SA_ID="$(az storage account show -g "$RG" -n "$SA" --query id -o tsv)"
az rest --method put \
    --url "https://management.azure.com${SA_ID}/blobServices/default/containers/backups?api-version=2023-05-01" \
    --body '{"properties":{"publicAccess":"None"}}' -o none
az storage account management-policy create -g "$RG" --account-name "$SA" --policy '{
  "rules": [{"enabled": true, "name": "expire-backups", "type": "Lifecycle",
    "definition": {"filters": {"blobTypes": ["blockBlob"], "prefixMatch": ["backups/"]},
      "actions": {"baseBlob": {"delete": {"daysAfterModificationGreaterThan": 30}}}}}]}' -o none
az role assignment create --assignee-object-id "$VM_PRINCIPAL" --assignee-principal-type ServicePrincipal \
    --role "Storage Blob Data Contributor" \
    --scope "$SA_ID/blobServices/default/containers/backups" -o none 2>/dev/null || true

step "GitHub deploy identity (OIDC, no secret): may run commands on this VM only"
APP_ID="$(az ad app list --display-name giridih-deploy-github --query '[0].appId' -o tsv)"
if [[ -z "$APP_ID" ]]; then
    APP_ID="$(az ad app create --display-name giridih-deploy-github --query appId -o tsv)"
    az ad sp create --id "$APP_ID" -o none
fi
SUBJECT="repo:${REPO}:environment:azure-production"
if ! az ad app federated-credential list --id "$APP_ID" --query "[?subject=='$SUBJECT']" -o tsv | grep -q .; then
    az ad app federated-credential create --id "$APP_ID" --parameters "{
      \"name\": \"github-azure-production\", \"issuer\": \"https://token.actions.githubusercontent.com\",
      \"subject\": \"$SUBJECT\", \"audiences\": [\"api://AzureADTokenExchange\"]}" -o none
fi
SP_ID="$(az ad sp show --id "$APP_ID" --query id -o tsv)"
az role assignment create --assignee-object-id "$SP_ID" --assignee-principal-type ServicePrincipal \
    --role "Virtual Machine Contributor" --scope "$VM_ID" -o none 2>/dev/null || true

echo
echo "Outbound IP (allowlist in Supabase): $(az network public-ip show -g "$RG" -n giridih-ip --query ipAddress -o tsv)"
echo "Backup storage account:              $SA"
echo "GitHub secrets: AZURE_CLIENT_ID=$APP_ID AZURE_TENANT_ID=$(az account show --query tenantId -o tsv) AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION"
