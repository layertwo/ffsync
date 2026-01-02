# Design Document

## Overview

The Firefox Sync Authentication Frontend is a single-page web application (SPA) that helps users authenticate with their OIDC provider (Authentik, Authelia, etc.) and obtain the Token Server URI needed to configure Firefox Sync. The application implements the OAuth 2.0 authorization code flow with PKCE entirely in the browser, making it deployable as a static website without requiring a backend server.

The frontend acts as a simple authentication helper that:
1. Initiates OAuth flow with the configured OIDC provider
2. Handles the OAuth callback and token exchange
3. Validates authentication by calling the Token Server
4. Displays the Token Server URI and configuration instructions

This design prioritizes simplicity, security, and ease of deployment while providing a user-friendly experience for configuring Firefox Sync with custom identity providers.

## Architecture

### High-Level Architecture

```
┌─────────────┐         ┌──────────────────┐         ┌─────────────┐
│   Firefox   │         │  Auth Frontend   │         │  Authentik  │
│    User     │────────▶│   (Static SPA)   │────────▶│    OIDC     │
└─────────────┘         └──────────────────┘         └─────────────┘
                                │                            │
                                │                            │
                                ▼                            ▼
                        ┌──────────────────┐         ┌─────────────┐
                        │  Token Server    │         │   OAuth     │
                        │  /1.0/sync/1.5   │         │  Callback   │
                        └──────────────────┘         └─────────────┘
```

### Application States

The application operates in four distinct states:

1. **Initial State**: Landing page with authentication button
2. **Authenticating State**: User redirected to OIDC provider
3. **Processing State**: Handling OAuth callback and token exchange
4. **Success State**: Displaying Token Server URI and instructions

### Technology Stack

- **HTML5**: Semantic markup for structure
- **CSS3**: Responsive styling with mobile-first approach
- **TypeScript**: Type-safe development with strict mode enabled
- **Web Crypto API**: For PKCE code verifier and challenge generation
- **Fetch API**: For HTTP requests to OIDC provider and Token Server
- **sessionStorage**: For temporary state management during OAuth flow

### Deployment Model

The application is designed for static hosting with AWS CDK infrastructure:

**Primary Deployment (AWS CDK)**:
- **S3 Bucket**: Hosts static files (HTML, CSS, JS, config.json)
- **CloudFront Distribution**: CDN for global delivery and HTTPS
- **Route53** (optional): Custom domain configuration
- **ACM Certificate** (optional): SSL/TLS certificate for custom domain

**CDK Stack Structure**:
```typescript
// lib/stacks/auth-frontend.ts
export class AuthFrontendStack extends Stack {
  constructor(scope: Construct, id: string, props: AuthFrontendStackProps) {
    // S3 bucket for static website hosting
    const websiteBucket = new s3.Bucket(this, 'AuthFrontendBucket', {
      websiteIndexDocument: 'index.html',
      websiteErrorDocument: 'error.html',
      publicReadAccess: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ACLS,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // CloudFront distribution
    const distribution = new cloudfront.Distribution(this, 'AuthFrontendDistribution', {
      defaultBehavior: {
        origin: new origins.S3Origin(websiteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
      },
      defaultRootObject: 'index.html',
      errorResponses: [
        {
          httpStatus: 404,
          responseHttpStatus: 200,
          responsePagePath: '/index.html',
        },
      ],
    });

    // Deploy website files
    new s3deploy.BucketDeployment(this, 'DeployAuthFrontend', {
      sources: [s3deploy.Source.asset('./auth-frontend/dist')],
      destinationBucket: websiteBucket,
      distribution,
      distributionPaths: ['/*'],
    });

    // Outputs
    new CfnOutput(this, 'AuthFrontendUrl', {
      value: `https://${distribution.distributionDomainName}`,
      description: 'Auth Frontend URL',
    });
  }
}
```

**Alternative Deployment Options**:
- **GitHub Pages**: For open-source deployments
- **Netlify/Vercel**: For quick prototyping
- **Any static host**: Nginx, Apache, etc.

Configuration is provided via a `config.json` file that can be modified without rebuilding the application.

## Components and Interfaces

### 1. Configuration Manager

**Purpose**: Load and validate application configuration

**Interface**:
```typescript
class ConfigManager {
  async loadConfig(): Promise<Config>
  validateConfig(config: Config): ValidationResult
}

interface Config {
  oidcProviderUrl: string      // e.g., "https://auth.example.com"
  clientId: string              // OAuth client ID
  redirectUri: string           // e.g., "https://sync-auth.example.com/callback"
  tokenServerUrl: string        // e.g., "https://sync.example.com"
  scopes: string[]              // e.g., ["openid", "profile", "email"]
}
```

**Responsibilities**:
- Fetch `config.json` on application load
- Validate required configuration fields
- Provide configuration to other components
- Display error if configuration is invalid

### 2. OIDC Discovery Client

**Purpose**: Discover OIDC provider endpoints automatically

**Interface**:
```typescript
class OIDCDiscoveryClient {
  async discover(providerUrl: string): Promise<OIDCConfiguration>
  cacheConfiguration(config: OIDCConfiguration): void
  getCachedConfiguration(): OIDCConfiguration | null
}

interface OIDCConfiguration {
  authorizationEndpoint: string
  tokenEndpoint: string
  issuer: string
}
```

**Responsibilities**:
- Fetch `.well-known/openid-configuration` from OIDC provider
- Extract authorization and token endpoints
- Cache configuration in sessionStorage
- Handle discovery failures gracefully

### 3. PKCE Generator

**Purpose**: Generate PKCE code verifier and challenge for secure OAuth flow

**Interface**:
```typescript
class PKCEGenerator {
  generateCodeVerifier(): string
  async generateCodeChallenge(verifier: string): Promise<string>
}
```

**Responsibilities**:
- Generate cryptographically random code verifier (43-128 characters)
- Compute SHA-256 hash of verifier for code challenge
- Use Web Crypto API for secure random generation
- Base64-URL encode the challenge

**Implementation Details**:
- Code verifier: Random string from unreserved characters (A-Z, a-z, 0-9, -, ., _, ~)
- Code challenge: Base64-URL(SHA256(code_verifier))
- Challenge method: S256 (SHA-256)

### 4. OAuth Flow Manager

**Purpose**: Orchestrate the OAuth 2.0 authorization code flow

**Interface**:
```typescript
class OAuthFlowManager {
  async initiateFlow(): Promise<void>
  async handleCallback(params: URLSearchParams): Promise<AuthResult>
  async exchangeCodeForToken(code: string, codeVerifier: string): Promise<TokenResponse>
}

interface AuthResult {
  success: boolean
  accessToken?: string
  error?: string
  errorDescription?: string
}

interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  scope: string
}
```

**Responsibilities**:
- Generate state parameter for CSRF protection
- Generate PKCE parameters
- Construct authorization URL with all required parameters
- Redirect user to OIDC provider
- Handle OAuth callback and validate state
- Exchange authorization code for access token
- Handle OAuth errors

### 5. Session Manager

**Purpose**: Manage temporary session data during OAuth flow

**Interface**:
```typescript
class SessionManager {
  storeCodeVerifier(verifier: string): void
  getCodeVerifier(): string | null
  storeState(state: string): void
  getState(): string | null
  clear(): void
}
```

**Responsibilities**:
- Store code verifier in sessionStorage
- Store state parameter in sessionStorage
- Retrieve stored values for validation
- Clear session data after successful authentication
- Ensure data expires when tab closes

### 6. Token Server Client

**Purpose**: Validate authentication by calling the Token Server

**Interface**:
```typescript
class TokenServerClient {
  async validateToken(accessToken: string): Promise<ValidationResult>
}

interface ValidationResult {
  success: boolean
  tokenServerUri?: string
  error?: string
}
```

**Responsibilities**:
- Send GET request to Token Server with Bearer token
- Validate response status
- Extract Token Server URI from configuration
- Handle Token Server errors (401, 503, etc.)
- Return validation result

### 7. UI Controller

**Purpose**: Manage UI state and user interactions

**Interface**:
```typescript
class UIController {
  showLandingPage(): void
  showLoadingState(message: string): void
  showSuccessPage(tokenServerUri: string): void
  showErrorPage(error: string, details?: string): void
  copyToClipboard(text: string): Promise<void>
}
```

**Responsibilities**:
- Render different application states
- Handle button clicks and user interactions
- Display loading indicators
- Show success message with Token Server URI
- Provide copy-to-clipboard functionality
- Display error messages with troubleshooting info
- Render Firefox configuration instructions

### 8. Application Controller

**Purpose**: Main application orchestrator

**Interface**:
```typescript
class Application {
  async initialize(): Promise<void>
  async startAuthentication(): Promise<void>
  async handleOAuthCallback(): Promise<void>
  async restart(): Promise<void>
}
```

**Responsibilities**:
- Initialize all components
- Load and validate configuration
- Discover OIDC endpoints
- Coordinate OAuth flow
- Handle application lifecycle
- Manage error states

## Data Models

### Configuration Model

```typescript
interface Config {
  oidcProviderUrl: string      // Base URL of OIDC provider
  clientId: string              // OAuth client ID registered with provider
  redirectUri: string           // Callback URL for this application
  tokenServerUrl: string        // Base URL of Token Server
  scopes: string[]              // OAuth scopes to request
  appTitle?: string             // Optional custom title
  appDescription?: string       // Optional custom description
}
```

### OIDC Configuration Model

```typescript
interface OIDCConfiguration {
  issuer: string                      // OIDC provider issuer URL
  authorizationEndpoint: string       // Authorization endpoint URL
  tokenEndpoint: string               // Token endpoint URL
  jwksUri?: string                    // JWKS endpoint (not used in this design)
  scopesSupported?: string[]          // Supported scopes
  responseTypesSupported?: string[]   // Supported response types
}
```

### OAuth State Model

```typescript
interface OAuthState {
  codeVerifier: string          // PKCE code verifier
  state: string                 // CSRF protection state
  timestamp: number             // When state was created
}
```

### Token Response Model

```typescript
interface TokenResponse {
  access_token: string          // OAuth access token
  token_type: string            // Always "Bearer"
  expires_in: number            // Token lifetime in seconds
  scope: string                 // Granted scopes
  refresh_token?: string        // Optional refresh token (not used)
  id_token?: string             // Optional ID token (not used)
}
```

### Error Model

```typescript
interface OAuthError {
  error: string                 // OAuth error code
  error_description?: string    // Human-readable error description
  error_uri?: string            // URL with error information
}
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: PKCE Code Verifier Randomness

*For any* generated code verifier, the verifier should be cryptographically random with at least 256 bits of entropy and consist only of unreserved characters.

**Validates: Requirements 2.1, 2.2**

### Property 2: PKCE Code Challenge Correctness

*For any* code verifier, the code challenge should equal Base64-URL(SHA256(code_verifier)) and use challenge method S256.

**Validates: Requirements 2.3**

### Property 3: State Parameter Uniqueness

*For any* two OAuth flows initiated at different times, the state parameters should be different with overwhelming probability.

**Validates: Requirements 2.5**

### Property 4: State Validation

*For any* OAuth callback, if the state parameter does not match the stored state, the system should reject the callback and display an error.

**Validates: Requirements 4.3, 4.4**

### Property 5: Authorization URL Construction

*For any* authorization request, the constructed URL should include all required parameters: client_id, redirect_uri, response_type=code, scope, state, code_challenge, and code_challenge_method=S256.

**Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

### Property 6: Token Exchange Request Correctness

*For any* token exchange request, the request should include all required parameters: grant_type=authorization_code, code, redirect_uri, client_id, and code_verifier.

**Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6**

### Property 7: Session Data Isolation

*For any* browser tab or window, session data stored in sessionStorage should not be accessible from other tabs or windows.

**Validates: Requirements 2.7, 17.3**

### Property 8: Configuration Validation

*For any* configuration object, if any required field (oidcProviderUrl, clientId, redirectUri, tokenServerUrl) is missing or empty, the system should fail to initialize and display an error.

**Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5**

### Property 9: OIDC Discovery Success

*For any* valid OIDC provider URL, if the provider returns a valid discovery document, the system should extract and cache the authorization_endpoint and token_endpoint.

**Validates: Requirements 12.2, 12.3**

### Property 10: Token Server URI Display

*For any* successful authentication, the displayed Token Server URI should match the configured tokenServerUrl with the path /1.0/sync/1.5.

**Validates: Requirements 7.3, 7.4**

### Property 11: Clipboard Copy Success

*For any* copy operation, if the Clipboard API is available and the user grants permission, the Token Server URI should be copied to the clipboard exactly as displayed.

**Validates: Requirements 8.2**

### Property 12: Session Cleanup

*For any* successful authentication or error state, when the user clicks restart or clear, all session data (code verifier, state) should be removed from sessionStorage.

**Validates: Requirements 17.2, 17.4, 17.5**

### Property 13: Error State Handling

*For any* error during the OAuth flow (invalid state, token exchange failure, Token Server error), the system should display an error message and provide a restart button.

**Validates: Requirements 13.1, 13.4**

### Property 14: Browser API Availability

*For any* browser environment, if required APIs (Crypto, Fetch, sessionStorage) are not available, the system should display a compatibility warning before attempting authentication.

**Validates: Requirements 18.2, 18.3, 18.4**

### Property 15: Loading State Visibility

*For any* asynchronous operation (OIDC discovery, token exchange, Token Server validation), a loading indicator should be visible during the operation and hidden upon completion.

**Validates: Requirements 16.1, 16.2, 16.3, 16.5**

## Error Handling

### Error Categories

#### 1. Configuration Errors

**Causes**:
- Missing or invalid `config.json`
- Required configuration fields missing
- Invalid URLs in configuration

**Handling**:
- Display error message on landing page
- Show which configuration fields are missing
- Provide example configuration
- Prevent authentication flow from starting

**User Experience**:
```
Configuration Error

The application is not properly configured. Please check the following:
- OIDC Provider URL is required
- Client ID is required
- Redirect URI is required
- Token Server URL is required

Contact your administrator for assistance.
```

#### 2. OIDC Discovery Errors

**Causes**:
- OIDC provider unreachable
- Invalid discovery document
- Missing required endpoints

**Handling**:
- Display error with provider URL
- Suggest checking network connectivity
- Suggest verifying provider URL
- Allow retry

**User Experience**:
```
Discovery Failed

Could not discover OIDC endpoints from:
https://auth.example.com

Troubleshooting:
- Check that the OIDC provider is accessible
- Verify the provider URL is correct
- Check your network connection

[Retry] [Contact Support]
```

#### 3. OAuth Flow Errors

**Causes**:
- User denies authorization
- Invalid state parameter (CSRF)
- Authorization code expired
- PKCE validation failure

**Handling**:
- Extract error and error_description from callback
- Display user-friendly error message
- Provide restart button
- Log technical details to console

**User Experience**:
```
Authentication Failed

access_denied: User denied authorization

You can try again or contact your administrator if the problem persists.

[Try Again]
```

#### 4. Token Exchange Errors

**Causes**:
- Network failure
- Invalid authorization code
- PKCE verification failure
- OIDC provider error

**Handling**:
- Display error from token endpoint
- Suggest possible causes
- Provide restart button
- Log full error to console

**User Experience**:
```
Token Exchange Failed

invalid_grant: The authorization code is invalid or expired

This can happen if:
- You took too long to complete authentication
- The authorization code was already used
- There was a browser compatibility issue

[Try Again]
```

#### 5. Token Server Errors

**Causes**:
- Token Server unreachable (503)
- Invalid access token (401)
- Network failure

**Handling**:
- Display specific error based on status code
- Suggest checking Token Server availability
- Provide restart button
- Show Token Server URL for debugging

**User Experience**:
```
Token Server Validation Failed

The Token Server returned an error (401 Unauthorized)

This usually means:
- The access token is invalid or expired
- The Token Server is not configured to accept tokens from this OIDC provider

Token Server: https://sync.example.com/1.0/sync/1.5

[Try Again] [Contact Support]
```

#### 6. Browser Compatibility Errors

**Causes**:
- Missing Web Crypto API
- Missing Fetch API
- Missing sessionStorage

**Handling**:
- Check for required APIs on load
- Display compatibility warning
- Suggest modern browser
- Prevent authentication if critical APIs missing

**User Experience**:
```
Browser Compatibility Warning

Your browser does not support required features:
- Web Crypto API (required for secure authentication)

Please use a modern browser:
- Firefox 34+
- Chrome 37+
- Safari 11+
- Edge 79+
```

### Error Recovery

All errors provide a "Try Again" or "Restart" button that:
1. Clears all session data
2. Resets application to initial state
3. Allows user to retry authentication

### Error Logging

All errors are logged to browser console with:
- Error type and message
- Stack trace (if available)
- Relevant context (URLs, parameters)
- Timestamp

Example:
```typescript
console.error('[AuthFrontend] Token exchange failed', {
  error: 'invalid_grant',
  description: 'Authorization code expired',
  timestamp: new Date().toISOString(),
  provider: 'https://auth.example.com'
});
```

## Testing Strategy

### Dual Testing Approach

This application will use both unit tests and property-based tests to ensure correctness:

- **Unit tests**: Verify specific examples, edge cases, and error conditions
- **Property tests**: Verify universal properties across all inputs

Both types of tests are complementary and necessary for comprehensive coverage.

### Unit Testing

**Framework**: Jest (or Vitest for faster execution)

**Test Organization**:
```
tests/
├── unit/
│   ├── config-manager.test.js
│   ├── oidc-discovery.test.js
│   ├── pkce-generator.test.js
│   ├── oauth-flow-manager.test.js
│   ├── session-manager.test.js
│   ├── token-server-client.test.js
│   └── ui-controller.test.js
├── integration/
│   └── full-flow.test.js
└── fixtures/
    ├── mock-config.json
    ├── mock-oidc-discovery.json
    └── mock-token-response.json
```

**Unit Test Coverage**:

1. **Configuration Manager**:
   - Valid configuration loads successfully
   - Missing required fields trigger errors
   - Invalid URLs are rejected
   - Optional fields have defaults

2. **OIDC Discovery Client**:
   - Valid discovery document is parsed
   - Missing endpoints trigger errors
   - Configuration is cached in sessionStorage
   - Network errors are handled

3. **PKCE Generator**:
   - Code verifier has correct length (43-128 chars)
   - Code verifier uses only unreserved characters
   - Code challenge is correct SHA-256 hash
   - Code challenge is Base64-URL encoded

4. **OAuth Flow Manager**:
   - Authorization URL includes all required parameters
   - State parameter is validated on callback
   - Invalid state triggers error
   - Token exchange includes all required parameters
   - OAuth errors are extracted and displayed

5. **Session Manager**:
   - Data is stored in sessionStorage
   - Data is retrieved correctly
   - Clear removes all data
   - Missing data returns null

6. **Token Server Client**:
   - Successful validation returns Token Server URI
   - 401 error is handled
   - 503 error is handled
   - Network errors are handled

7. **UI Controller**:
   - Landing page renders correctly
   - Success page displays Token Server URI
   - Error page displays error message
   - Copy to clipboard works
   - Loading states are shown/hidden

### Property-Based Testing

**Framework**: fast-check (JavaScript property testing library)

**Configuration**: Each property test runs minimum 100 iterations

**Property Test Coverage**:

1. **Property 1: PKCE Code Verifier Randomness**
   - Generate 100 code verifiers
   - Verify each has 43-128 characters
   - Verify each uses only [A-Za-z0-9-._~]
   - Verify all are unique
   - **Feature: auth-frontend, Property 1: PKCE Code Verifier Randomness**

2. **Property 2: PKCE Code Challenge Correctness**
   - Generate random code verifiers
   - Compute code challenge
   - Verify challenge = Base64-URL(SHA256(verifier))
   - **Feature: auth-frontend, Property 2: PKCE Code Challenge Correctness**

3. **Property 3: State Parameter Uniqueness**
   - Generate 100 state parameters
   - Verify all are unique
   - Verify each has sufficient entropy
   - **Feature: auth-frontend, Property 3: State Parameter Uniqueness**

4. **Property 5: Authorization URL Construction**
   - Generate random valid configurations
   - Construct authorization URL
   - Verify all required parameters present
   - Verify parameter values are correct
   - **Feature: auth-frontend, Property 5: Authorization URL Construction**

5. **Property 6: Token Exchange Request Correctness**
   - Generate random authorization codes and verifiers
   - Construct token exchange request
   - Verify all required parameters present
   - Verify parameter values are correct
   - **Feature: auth-frontend, Property 6: Token Exchange Request Correctness**

6. **Property 8: Configuration Validation**
   - Generate configurations with missing fields
   - Verify validation fails for each missing required field
   - Generate valid configurations
   - Verify validation succeeds
   - **Feature: auth-frontend, Property 8: Configuration Validation**

7. **Property 11: Clipboard Copy Success**
   - Generate random Token Server URIs
   - Mock Clipboard API
   - Verify copied text matches input exactly
   - **Feature: auth-frontend, Property 11: Clipboard Copy Success**

### Integration Testing

**Full Flow Test**:
1. Mock OIDC provider endpoints
2. Mock Token Server endpoint
3. Simulate complete OAuth flow
4. Verify success state is reached
5. Verify Token Server URI is displayed

**Error Flow Tests**:
1. Test OAuth error callback
2. Test token exchange failure
3. Test Token Server 401 error
4. Test Token Server 503 error
5. Test network failures

### Manual Testing Checklist

- [ ] Test with Authentik OIDC provider
- [ ] Test with Authelia OIDC provider
- [ ] Test on desktop browsers (Chrome, Firefox, Safari, Edge)
- [ ] Test on mobile browsers (iOS Safari, Android Chrome)
- [ ] Test copy to clipboard functionality
- [ ] Test error states and recovery
- [ ] Test with invalid configuration
- [ ] Test with unreachable OIDC provider
- [ ] Test with unreachable Token Server
- [ ] Verify instructions are clear and accurate
- [ ] Test responsive design on different screen sizes

### Test Execution

```bash
# Run all tests
npm test

# Run unit tests only
npm run test:unit

# Run property tests only
npm run test:property

# Run integration tests only
npm run test:integration

# Run tests with coverage
npm run test:coverage

# Run tests in watch mode
npm run test:watch
```

### Coverage Requirements

- **Unit test coverage**: Aim for 90%+ code coverage
- **Property test coverage**: All correctness properties must have corresponding tests
- **Integration test coverage**: All user flows must be tested end-to-end

### Continuous Integration

Tests should run automatically on:
- Every commit to main branch
- Every pull request
- Before deployment

CI should fail if:
- Any test fails
- Code coverage drops below threshold
- Property tests find counterexamples
