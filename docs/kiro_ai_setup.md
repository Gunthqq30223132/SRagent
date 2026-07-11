# Connecting Kiro AI in OmniRoute

Kiro AI provides the `kr/claude-sonnet-4.5` model (among other free tiers) and is configured as a primary model in the `anesthos-brain` combo chain. 

Since Antigravity OAuth is already configured, follow these instructions to establish the Kiro AI connection in OmniRoute.

---

## Method 1: Using the OmniRoute Dashboard (Recommended)

1. Ensure OmniRoute is running:
   ```bash
   PORT=20128 DATA_DIR=~/.omniroute omniroute
   ```
2. Open your web browser and navigate to the **OmniRoute Dashboard**:
   ```
   http://localhost:20128
   ```
3. Go to the **Providers** tab from the left sidebar.
4. Locate **Kiro AI** under the *OAuth / CLI Providers* section.
5. Click **Connect**.
6. This will trigger the AWS SSO/Builder ID OIDC device-code authorization:
   - A browser tab will open requesting authorization on AWS.
   - Enter your **AWS Builder ID** or AWS account credentials when prompted.
   - Authorize the connection.
7. Once authorized, OmniRoute will automatically poll the OIDC tokens, refresh them in the background, and mark the **Kiro AI** connection as active.

---

## Method 2: Headless CLI Setup (For Remote/VPS Sessions)

If you are running a headless server or VPS where the loopback redirect `127.0.0.1` is unreachable:

1. On your **local machine** (where the browser is available), execute:
   ```bash
   omniroute login antigravity
   ```
   *(Note: The login helper uses the same AWS OIDC authentication framework for both Antigravity and Kiro)*
2. Complete the authentication in your browser.
3. The CLI will output a single-line credential token blob.
4. Copy the credential blob.
5. Navigate to your remote/headless OmniRoute dashboard (`http://<server-ip>:20128`), go to **Providers** -> **Kiro AI** -> **Connect**, and click **Paste Credentials**.
6. Paste the credential blob and save. The remote OmniRoute instance will decode the token, finalize the OAuth state, and establish the Kiro connection.
