# FFSync Tools

Command-line tools for interacting with the Firefox Sync (FFSync) storage API.

## Installation

```bash
cd tools
pip install -r requirements.txt
```

## Quick Start

### 1. Get HAWK Credentials

First, obtain HAWK credentials by authenticating via OIDC:

```bash
python get_hawk_token.py \
  --issuer https://auth.example.com/application/o/myapp/ \
  --client-id my-client-id \
  --token-server-url https://sync.example.com \
  --json-only > hawk_creds.json
```

This will:
- Open your browser for OAuth login
- Exchange the OIDC token for HAWK credentials
- Save credentials to `hawk_creds.json`

### 2. Use the Storage API Client

Use the HAWK credentials to interact with the storage API:

```bash
# Using credentials file
python ffsync_client.py --credentials-file hawk_creds.json info collections

# Or set environment variables
export HAWK_ID="your-hawk-id"
export HAWK_KEY="your-hawk-key"
export HAWK_API_ENDPOINT="https://sync.example.com/storage"
python ffsync_client.py info collections
```

## Tools

### get_hawk_token.py

Obtains HAWK credentials via OIDC authentication flow.

**Options:**
- `--issuer` - OIDC issuer URL (required)
- `--client-id` - OAuth client ID (required)
- `--token-server-url` - Token server URL (required)
- `--client-secret` - OAuth client secret (optional, for confidential clients)
- `--scopes` - OAuth scopes (default: "openid profile email")
- `--port` - Local callback server port (default: 8765)
- `--json-only` - Output only JSON (useful for piping to file)
- `--debug` - Print debug information

**Example:**
```bash
python get_hawk_token.py \
  --issuer https://auth.example.com/application/o/myapp/ \
  --client-id my-client-id \
  --token-server-url https://sync.example.com \
  --json-only > hawk_creds.json
```

### ffsync_client.py

Comprehensive CLI for interacting with the FFSync storage API using HAWK authentication.

**Authentication Options:**
- `--hawk-id` - HAWK credential ID (or set `HAWK_ID` env var)
- `--hawk-key` - HAWK credential key (or set `HAWK_KEY` env var)
- `--api-endpoint` - API endpoint URL (or set `HAWK_API_ENDPOINT` env var)
- `--credentials-file` - JSON file with HAWK credentials
- `--algorithm` - HAWK hash algorithm (default: sha256)

**Commands:**

#### Info Commands
Get storage metadata and statistics:

```bash
# Get collection metadata
python ffsync_client.py --credentials-file hawk_creds.json info collections

# Get object counts per collection
python ffsync_client.py --credentials-file hawk_creds.json info counts

# Get storage usage per collection
python ffsync_client.py --credentials-file hawk_creds.json info usage

# Get quota information
python ffsync_client.py --credentials-file hawk_creds.json info quota
```

#### Collection Commands
Manage collections:

```bash
# List all collections
python ffsync_client.py --credentials-file hawk_creds.json collection list

# Create a collection
python ffsync_client.py --credentials-file hawk_creds.json collection create bookmarks

# Get collection metadata
python ffsync_client.py --credentials-file hawk_creds.json collection get bookmarks

# Delete a collection
python ffsync_client.py --credentials-file hawk_creds.json collection delete bookmarks --yes
```

#### BSO (Basic Storage Object) Commands
Manage individual storage objects:

```bash
# Get a BSO
python ffsync_client.py --credentials-file hawk_creds.json bso get bookmarks my-bookmark-id

# Update a BSO
python ffsync_client.py --credentials-file hawk_creds.json bso update \
  bookmarks my-bookmark-id '{"title":"Example","url":"https://example.com"}' \
  --sortindex 100 --ttl 3600

# Delete a BSO
python ffsync_client.py --credentials-file hawk_creds.json bso delete \
  bookmarks my-bookmark-id --yes
```

#### Storage Commands
Manage all storage:

```bash
# Delete all storage data (use with caution!)
python ffsync_client.py --credentials-file hawk_creds.json storage delete-all --yes
```

## Environment Variables

You can set these environment variables to avoid passing credentials on every command:

```bash
export HAWK_ID="your-hawk-id"
export HAWK_KEY="your-hawk-key"
export HAWK_API_ENDPOINT="https://sync.example.com/storage"

# Now you can run commands without --credentials-file
python ffsync_client.py info collections
```

## HAWK Credential Expiration

HAWK credentials expire after 300 seconds (5 minutes). When they expire, you'll need to run `get_hawk_token.py` again to obtain fresh credentials.

## Examples

### Complete Workflow

```bash
# 1. Get HAWK credentials
python get_hawk_token.py \
  --issuer https://auth.example.com/application/o/myapp/ \
  --client-id my-client-id \
  --token-server-url https://sync.example.com \
  --json-only > hawk_creds.json

# 2. Check storage info
python ffsync_client.py --credentials-file hawk_creds.json info collections

# 3. Create a collection and add data
python ffsync_client.py --credentials-file hawk_creds.json collection create bookmarks

# 4. Add a bookmark
python ffsync_client.py --credentials-file hawk_creds.json bso update \
  bookmarks bookmark-1 '{"title":"Mozilla","url":"https://mozilla.org"}' \
  --sortindex 1

# 5. Retrieve the bookmark
python ffsync_client.py --credentials-file hawk_creds.json bso get bookmarks bookmark-1

# 6. Check usage
python ffsync_client.py --credentials-file hawk_creds.json info usage
```

### Using with Shell Scripts

```bash
#!/bin/bash
# refresh_hawk_creds.sh - Refresh HAWK credentials

python get_hawk_token.py \
  --issuer "$OIDC_ISSUER" \
  --client-id "$OIDC_CLIENT_ID" \
  --token-server-url "$TOKEN_SERVER_URL" \
  --json-only > ~/.ffsync_hawk_creds.json

echo "HAWK credentials refreshed"
```

Then use in your scripts:

```bash
python ffsync_client.py --credentials-file ~/.ffsync_hawk_creds.json info collections
```

## Troubleshooting

### Authentication Errors

If you get authentication errors:
1. Check that your HAWK credentials haven't expired (300s lifetime)
2. Verify the API endpoint URL is correct
3. Ensure the HAWK ID and key match what was returned from the token server

### Connection Errors

If you can't connect to the API:
1. Verify the API endpoint is accessible
2. Check network connectivity
3. Ensure the token server URL is correct

### OIDC Errors

If OIDC authentication fails:
1. Verify the issuer URL is correct
2. Check that the client ID is valid
3. Ensure the redirect URI is configured in your OIDC provider
4. Try using `--debug` flag for more information
