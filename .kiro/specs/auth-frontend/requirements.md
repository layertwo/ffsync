# Requirements Document

## Introduction

This document specifies the requirements for implementing a simple web-based authentication helper for Firefox Sync. The frontend provides a user-friendly interface where users can authenticate with their existing Authentik (or other OIDC provider) account, obtain HAWK credentials from the Token Server, and receive clear instructions for configuring Firefox Sync manually. This is a browser-based equivalent of the `get_hawk_token.py` command-line tool, designed to be deployed as a static web application on S3, CloudFront, or any static hosting service.

## Glossary

- **Auth Frontend**: The simple web application that helps users obtain sync credentials
- **Authentik**: The OIDC provider used for user authentication (or other OIDC providers like Authelia, Pocket ID)
- **OAuth Flow**: The OAuth 2.0 authorization code flow with PKCE used to authenticate with Authentik
- **Authorization Code**: A temporary code exchanged for an access token
- **Access Token**: The OIDC token obtained from Authentik, used to authenticate with the Token Server
- **Token Server**: The backend service at `/1.0/sync/1.5` that exchanges OIDC tokens for HAWK credentials
- **HAWK Credentials**: The authentication credentials (id, key, api_endpoint, uid) needed to configure Firefox Sync
- **Client ID**: The OAuth client identifier registered in Authentik for this application
- **Redirect URI**: The callback URL where Authentik sends the authorization code after authentication
- **PKCE**: Proof Key for Code Exchange, a security extension for OAuth public clients
- **Code Verifier**: A cryptographically random string used in PKCE flow
- **Code Challenge**: A SHA-256 hash of the code verifier, sent during authorization
- **State Parameter**: A random value used to prevent CSRF attacks in OAuth flow
- **Token Server URI**: The URL that must be configured in Firefox's about:config (identity.sync.tokenserver.uri)

## Requirements

### Requirement 1

**User Story:** As a Firefox user, I want to visit a simple web page to start the authentication process, so that I can obtain sync credentials.

#### Acceptance Criteria

1. WHEN a user visits the auth frontend landing page, THE System SHALL display a welcome message explaining the purpose
2. WHEN a user visits the landing page, THE System SHALL display a button to begin authentication with Authentik
3. WHEN a user visits the landing page, THE System SHALL display a brief explanation of what will happen
4. WHEN a user visits the landing page, THE System SHALL indicate that HAWK credentials expire after 300 seconds
5. WHEN the landing page loads, THE System SHALL check if the user is returning from an OAuth callback

### Requirement 2

**User Story:** As a Firefox user, I want to authenticate with Authentik securely, so that my credentials cannot be intercepted.

#### Acceptance Criteria

1. WHEN a user clicks the authentication button, THE System SHALL generate a cryptographically random code verifier for PKCE
2. WHEN the System generates a code verifier, THE code verifier SHALL be a random string of 43-128 characters from the unreserved character set
3. WHEN the System generates a code verifier, THE System SHALL compute a code challenge by SHA-256 hashing the code verifier
4. WHEN the System generates a code verifier, THE System SHALL store it in browser sessionStorage
5. WHEN a user clicks the authentication button, THE System SHALL generate a random state parameter
6. WHEN the System generates a state parameter, THE System SHALL store it in browser sessionStorage
7. WHEN the System stores sensitive data, THE System SHALL use sessionStorage to ensure it expires when the tab closes

### Requirement 3

**User Story:** As a Firefox user, I want to be redirected to Authentik for authentication, so that I can log in with my existing account.

#### Acceptance Criteria

1. WHEN a user clicks the authentication button, THE System SHALL redirect to Authentik's authorization endpoint
2. WHEN the System constructs the authorization URL, THE System SHALL include the client_id parameter
3. WHEN the System constructs the authorization URL, THE System SHALL include the redirect_uri parameter pointing back to the frontend
4. WHEN the System constructs the authorization URL, THE System SHALL include the response_type parameter set to "code"
5. WHEN the System constructs the authorization URL, THE System SHALL include the scope parameter with at least "openid profile email"
6. WHEN the System constructs the authorization URL, THE System SHALL include the state parameter
7. WHEN the System constructs the authorization URL, THE System SHALL include the code_challenge parameter
8. WHEN the System constructs the authorization URL, THE System SHALL include the code_challenge_method parameter set to "S256"

### Requirement 4

**User Story:** As a Firefox user, I want to be redirected back to the frontend after authentication, so that I can complete the credential exchange.

#### Acceptance Criteria

1. WHEN Authentik redirects back to the frontend, THE System SHALL receive an authorization code in the URL query parameters
2. WHEN Authentik redirects back to the frontend, THE System SHALL receive the state parameter in the URL query parameters
3. WHEN the System receives the callback, THE System SHALL validate that the state parameter matches the stored value
4. WHEN the state parameter does not match, THE System SHALL display an error message indicating a potential CSRF attack
5. WHEN the state parameter is missing, THE System SHALL display an error message
6. WHEN Authentik returns an error parameter, THE System SHALL display the error description to the user

### Requirement 5

**User Story:** As a Firefox user, I want the frontend to exchange my authorization code for an access token, so that I can authenticate with the Token Server.

#### Acceptance Criteria

1. WHEN the System receives a valid authorization code, THE System SHALL send a POST request to Authentik's token endpoint
2. WHEN the System constructs the token request, THE System SHALL include the grant_type parameter set to "authorization_code"
3. WHEN the System constructs the token request, THE System SHALL include the code parameter with the authorization code
4. WHEN the System constructs the token request, THE System SHALL include the redirect_uri parameter matching the original request
5. WHEN the System constructs the token request, THE System SHALL include the client_id parameter
6. WHEN the System constructs the token request, THE System SHALL include the code_verifier parameter for PKCE validation
7. WHEN the token endpoint returns a successful response, THE System SHALL extract the access_token from the JSON response
8. WHEN the token exchange fails, THE System SHALL display an error message with the failure reason

### Requirement 6

**User Story:** As a Firefox user, I want the frontend to obtain HAWK credentials from the Token Server, so that I can configure Firefox Sync.

#### Acceptance Criteria

1. WHEN the System obtains an access token from Authentik, THE System SHALL send a GET request to the Token Server at `/1.0/sync/1.5`
2. WHEN the System sends the Token Server request, THE System SHALL include an Authorization header with "Bearer {access_token}"
3. WHEN the Token Server returns a successful response, THE System SHALL extract the id, key, uid, api_endpoint, and duration fields
4. WHEN the Token Server request fails with 401, THE System SHALL display an error indicating invalid or expired token
5. WHEN the Token Server request fails with 503, THE System SHALL display an error indicating the service is unavailable
6. WHEN the Token Server request fails, THE System SHALL display the error details for debugging

### Requirement 7

**User Story:** As a Firefox user, I want to see a success message after authentication, so that I know the process worked.

#### Acceptance Criteria

1. WHEN the System successfully obtains HAWK credentials from the Token Server, THE System SHALL display a success message
2. WHEN the System displays the success message, THE System SHALL confirm that authentication was successful
3. WHEN the System displays the success message, THE System SHALL display the Token Server URI prominently
4. WHEN the System displays the Token Server URI, THE URI SHALL be the base URL (e.g., https://sync.example.com/1.0/sync/1.5)
5. WHEN the System displays the success message, THE System SHALL NOT display the HAWK credentials (id, key, api_endpoint, uid)

### Requirement 8

**User Story:** As a Firefox user, I want to copy the Token Server URI easily, so that I can paste it into Firefox configuration.

#### Acceptance Criteria

1. WHEN the System displays the Token Server URI, THE System SHALL provide a copy button
2. WHEN a user clicks the copy button, THE System SHALL copy the Token Server URI to the clipboard
3. WHEN the URI is copied, THE System SHALL display a visual confirmation message
4. WHEN the System uses the Clipboard API, THE System SHALL handle browsers that don't support it gracefully
5. WHEN the Clipboard API is unavailable, THE System SHALL provide a fallback method to select the text

### Requirement 9

**User Story:** As a Firefox user, I want clear instructions on how to configure Firefox Sync, so that I can complete the setup.

#### Acceptance Criteria

1. WHEN the System displays the success message, THE System SHALL provide step-by-step instructions for configuring Firefox
2. WHEN the System provides instructions, THE System SHALL explain that the Token Server URI must be set BEFORE signing into Firefox Sync
3. WHEN the System provides instructions, THE System SHALL explain how to open about:config in Firefox
4. WHEN the System provides instructions, THE System SHALL specify the exact preference name: identity.sync.tokenserver.uri
5. WHEN the System provides instructions, THE System SHALL explain how to set the preference value to the displayed Token Server URI
6. WHEN the System provides instructions, THE System SHALL explain that users should then sign into Firefox Sync normally
7. WHEN the System provides instructions, THE System SHALL explain that Firefox will automatically obtain credentials from the Token Server

### Requirement 10

**User Story:** As a Firefox user, I want to authenticate again if needed, so that I can verify my setup.

#### Acceptance Criteria

1. WHEN the System displays the success message, THE System SHALL provide a button to start a new authentication flow
2. WHEN a user clicks the re-authenticate button, THE System SHALL clear all stored session data
3. WHEN a user clicks the re-authenticate button, THE System SHALL restart the OAuth flow from the beginning
4. WHEN the System displays the success message, THE System SHALL explain that re-authentication is only needed for testing
5. WHEN the System displays the success message, THE System SHALL explain that Firefox will handle authentication automatically once configured

### Requirement 11

**User Story:** As a developer, I want the frontend to be configurable, so that it works with different OIDC providers and Token Server deployments.

#### Acceptance Criteria

1. WHEN the System loads, THE System SHALL read the OIDC provider URL from a configuration file or environment
2. WHEN the System loads, THE System SHALL read the OAuth client ID from configuration
3. WHEN the System loads, THE System SHALL read the Token Server URL from configuration
4. WHEN the System loads, THE System SHALL read the redirect URI from configuration
5. WHEN configuration values are missing, THE System SHALL display an error message indicating misconfiguration
6. WHEN the System is deployed, THE configuration SHALL be easily modifiable without rebuilding the application

### Requirement 12

**User Story:** As a developer, I want the frontend to discover OIDC endpoints automatically, so that configuration is minimal.

#### Acceptance Criteria

1. WHEN the System starts, THE System SHALL fetch the OIDC provider's configuration from `.well-known/openid-configuration`
2. WHEN the System fetches OIDC configuration, THE System SHALL extract the authorization_endpoint
3. WHEN the System fetches OIDC configuration, THE System SHALL extract the token_endpoint
4. WHEN the OIDC discovery fails, THE System SHALL display an error message with troubleshooting guidance
5. WHEN the System caches OIDC configuration, THE System SHALL cache it in sessionStorage for the duration of the session

### Requirement 13

**User Story:** As a Firefox user, I want the frontend to handle errors gracefully, so that I understand what went wrong.

#### Acceptance Criteria

1. WHEN an error occurs during the OAuth flow, THE System SHALL display a user-friendly error message
2. WHEN Authentik returns an error in the callback, THE System SHALL extract and display the error description
3. WHEN a network request fails, THE System SHALL display an error indicating connectivity issues
4. WHEN the System displays an error, THE System SHALL provide a button to restart the authentication flow
5. WHEN the System encounters an unexpected error, THE System SHALL log the error details to the browser console for debugging

### Requirement 14

**User Story:** As a system administrator, I want the frontend to be a static web application, so that it can be easily deployed and hosted.

#### Acceptance Criteria

1. WHEN the System is built, THE System SHALL consist of static HTML, CSS, and JavaScript files
2. WHEN the System is deployed, THE System SHALL NOT require a backend server for the frontend logic
3. WHEN the System makes API calls, THE System SHALL make them directly from the browser to Authentik and the Token Server
4. WHEN the System is hosted, THE System SHALL be servable from any static file hosting service
5. WHEN the System is hosted, THE System SHALL support being served from S3, CloudFront, or any CDN

### Requirement 15

**User Story:** As a Firefox user, I want the frontend to work on mobile and desktop browsers, so that I can authenticate from any device.

#### Acceptance Criteria

1. WHEN the System renders the UI, THE System SHALL use responsive design that adapts to different screen sizes
2. WHEN a user accesses the frontend on a mobile device, THE System SHALL display a mobile-friendly interface
3. WHEN a user accesses the frontend on a desktop browser, THE System SHALL display a desktop-optimized interface
4. WHEN the System displays credentials, THE credentials SHALL be easily readable on small screens
5. WHEN the System provides buttons, THE buttons SHALL be easily tappable on touch devices

### Requirement 16

**User Story:** As a Firefox user, I want clear visual feedback during the authentication process, so that I know the system is working.

#### Acceptance Criteria

1. WHEN the System is exchanging the authorization code for a token, THE System SHALL display a loading indicator
2. WHEN the System is fetching HAWK credentials from the Token Server, THE System SHALL display a loading indicator
3. WHEN the System is discovering OIDC endpoints, THE System SHALL display a loading indicator
4. WHEN a loading indicator is displayed, THE System SHALL prevent duplicate requests
5. WHEN an operation completes, THE System SHALL hide the loading indicator and show the result

### Requirement 17

**User Story:** As a security-conscious user, I want the frontend to clear sensitive data after use, so that credentials are not left in browser storage.

#### Acceptance Criteria

1. WHEN credentials are displayed, THE System SHALL provide a button to clear all stored data
2. WHEN the user clicks the clear button, THE System SHALL remove all data from sessionStorage
3. WHEN the user closes the browser tab, THE System SHALL automatically clear sessionStorage
4. WHEN the System stores the code verifier, THE System SHALL remove it after successful token exchange
5. WHEN the System stores the state parameter, THE System SHALL remove it after validation

### Requirement 18

**User Story:** As a Firefox user, I want the frontend to validate my browser compatibility, so that I know if my browser supports the required features.

#### Acceptance Criteria

1. WHEN the System loads, THE System SHALL check for required browser APIs
2. WHEN the System detects missing Crypto API support, THE System SHALL display a warning about PKCE compatibility
3. WHEN the System detects missing Fetch API support, THE System SHALL display a warning about network request compatibility
4. WHEN the System detects missing sessionStorage support, THE System SHALL display a warning
5. WHEN the System detects an incompatible browser, THE System SHALL suggest using a modern browser
6. WHEN all required APIs are available, THE System SHALL proceed with normal operation

### Requirement 19

**User Story:** As a Firefox user, I want helpful troubleshooting information when things go wrong, so that I can resolve issues.

#### Acceptance Criteria

1. WHEN the System displays an error, THE System SHALL provide specific troubleshooting steps
2. WHEN authentication fails, THE System SHALL suggest checking Authentik configuration
3. WHEN the Token Server is unreachable, THE System SHALL suggest checking the Token Server URL
4. WHEN PKCE validation fails, THE System SHALL suggest browser compatibility issues
5. WHEN the System displays troubleshooting info, THE System SHALL include links to documentation if available

### Requirement 20

**User Story:** As a developer, I want the frontend to have a clean, simple UI, so that users can focus on the task.

#### Acceptance Criteria

1. WHEN the System renders the UI, THE System SHALL use a clean, minimal design
2. WHEN the System displays information, THE System SHALL use clear typography and spacing
3. WHEN the System displays buttons, THE buttons SHALL have clear labels indicating their action
4. WHEN the System displays the Token Server URI, THE System SHALL use a monospace font for the technical value
5. WHEN the System displays instructions, THE System SHALL use numbered steps for clarity

### Requirement 21

**User Story:** As a system administrator, I want the frontend to support multiple OIDC providers, so that it works with different identity systems.

#### Acceptance Criteria

1. WHEN the System is configured, THE System SHALL work with any OIDC-compliant provider
2. WHEN the System is configured for Authentik, THE System SHALL work without modifications
3. WHEN the System is configured for Authelia, THE System SHALL work without modifications
4. WHEN the System is configured for Pocket ID, THE System SHALL work without modifications
5. WHEN the System is configured for Keycloak, THE System SHALL work without modifications
6. WHEN the System discovers OIDC endpoints, THE System SHALL use standard OIDC discovery

### Requirement 22

**User Story:** As a Firefox user, I want to see what scopes are being requested, so that I understand what access is being granted.

#### Acceptance Criteria

1. WHEN the System displays the landing page, THE System SHALL show which OAuth scopes will be requested
2. WHEN the System requests scopes, THE System SHALL explain what each scope means
3. WHEN the System requests "openid" scope, THE System SHALL explain it provides basic identity
4. WHEN the System requests "profile" scope, THE System SHALL explain it provides profile information
5. WHEN the System requests "email" scope, THE System SHALL explain it provides email address

### Requirement 23

**User Story:** As a developer, I want the frontend to be easily customizable, so that it can match my organization's branding.

#### Acceptance Criteria

1. WHEN the System is deployed, THE System SHALL support custom CSS for styling
2. WHEN the System is deployed, THE System SHALL support custom logos and branding
3. WHEN the System is deployed, THE System SHALL support custom text and messaging
4. WHEN the System is deployed, THE System SHALL separate content from presentation
5. WHEN the System is customized, THE customization SHALL NOT require modifying core JavaScript logic

### Requirement 24

**User Story:** As a Firefox user, I want to understand the security of this authentication flow, so that I can trust the system.

#### Acceptance Criteria

1. WHEN the System displays the landing page, THE System SHALL explain that authentication happens through the user's OIDC provider
2. WHEN the System displays the landing page, THE System SHALL explain that no credentials are stored by the frontend
3. WHEN the System displays the landing page, THE System SHALL explain that PKCE is used to prevent authorization code interception
4. WHEN the System displays the success message, THE System SHALL explain that Firefox will securely obtain credentials when needed
5. WHEN the System displays the success message, THE System SHALL explain that the Token Server validates all requests
