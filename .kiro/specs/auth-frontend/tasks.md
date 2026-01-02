# Implementation Plan: Auth Frontend

## Overview

This implementation plan breaks down the auth frontend into discrete coding tasks. The approach follows a bottom-up strategy: building core utilities first, then components, then integration, and finally infrastructure. Each task builds on previous work and includes testing sub-tasks to validate functionality incrementally.

## Tasks

- [ ] 1. Set up project structure and configuration
  - Create `auth-frontend/` directory in project root
  - Create `src/`, `tests/`, and `dist/` subdirectories
  - Set up `package.json` with dependencies (jest, @types/jest, fast-check, typescript, esbuild)
  - Create `tsconfig.json` with strict mode enabled
  - Create `config.example.json` with sample configuration
  - Create `.gitignore` for node_modules and dist
  - _Requirements: 11.1, 11.2, 11.3, 11.4, 14.1_

- [ ] 2. Implement PKCE Generator
  - [ ] 2.1 Create `src/pkce-generator.ts` with PKCEGenerator class
    - Implement `generateCodeVerifier()` using Web Crypto API
    - Implement `generateCodeChallenge(verifier)` with SHA-256 hashing
    - Use Base64-URL encoding for challenge
    - Define TypeScript interfaces for return types
    - _Requirements: 2.1, 2.2, 2.3_

  - [ ]* 2.2 Write property test for PKCE code verifier randomness
    - **Property 1: PKCE Code Verifier Randomness**
    - **Validates: Requirements 2.1, 2.2**

  - [ ]* 2.3 Write property test for PKCE code challenge correctness
    - **Property 2: PKCE Code Challenge Correctness**
    - **Validates: Requirements 2.3**

  - [ ]* 2.4 Write unit tests for PKCE Generator
    - Test code verifier length (43-128 characters)
    - Test code verifier character set
    - Test code challenge format
    - _Requirements: 2.1, 2.2, 2.3_

- [ ] 3. Implement Session Manager
  - [ ] 3.1 Create `src/session-manager.ts` with SessionManager class
    - Implement `storeCodeVerifier(verifier)` using sessionStorage
    - Implement `getCodeVerifier()` to retrieve stored verifier
    - Implement `storeState(state)` using sessionStorage
    - Implement `getState()` to retrieve stored state
    - Implement `clear()` to remove all session data
    - Define TypeScript interfaces for session data
    - _Requirements: 2.4, 2.6, 17.2, 17.4, 17.5_

  - [ ]* 3.2 Write property test for session data isolation
    - **Property 7: Session Data Isolation**
    - **Validates: Requirements 2.7, 17.3**

  - [ ]* 3.3 Write unit tests for Session Manager
    - Test storing and retrieving code verifier
    - Test storing and retrieving state
    - Test clear removes all data
    - Test missing data returns null
    - _Requirements: 2.4, 2.6, 17.2_

- [ ] 4. Implement Configuration Manager
  - [ ] 4.1 Create `src/config-manager.ts` with ConfigManager class
    - Define Config interface with all required fields
    - Define ValidationResult interface
    - Implement `loadConfig()` to fetch config.json
    - Implement `validateConfig(config)` to check required fields
    - Validate oidcProviderUrl, clientId, redirectUri, tokenServerUrl
    - Return validation errors with missing field details
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

  - [ ]* 4.2 Write property test for configuration validation
    - **Property 8: Configuration Validation**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5**

  - [ ]* 4.3 Write unit tests for Configuration Manager
    - Test valid configuration loads successfully
    - Test missing oidcProviderUrl triggers error
    - Test missing clientId triggers error
    - Test missing redirectUri triggers error
    - Test missing tokenServerUrl triggers error
    - Test optional fields have defaults
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [ ] 5. Implement OIDC Discovery Client
  - [ ] 5.1 Create `src/oidc-discovery.ts` with OIDCDiscoveryClient class
    - Define OIDCConfiguration interface
    - Implement `discover(providerUrl)` to fetch .well-known/openid-configuration
    - Extract authorization_endpoint and token_endpoint
    - Implement `cacheConfiguration(config)` using sessionStorage
    - Implement `getCachedConfiguration()` to retrieve cached config
    - Handle network errors and invalid responses
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5_

  - [ ]* 5.2 Write property test for OIDC discovery success
    - **Property 9: OIDC Discovery Success**
    - **Validates: Requirements 12.2, 12.3**

  - [ ]* 5.3 Write unit tests for OIDC Discovery Client
    - Test valid discovery document is parsed
    - Test missing authorization_endpoint triggers error
    - Test missing token_endpoint triggers error
    - Test configuration is cached in sessionStorage
    - Test network errors are handled
    - _Requirements: 12.1, 12.2, 12.3, 12.4_

- [ ] 6. Implement OAuth Flow Manager
  - [ ] 6.1 Create `src/oauth-flow-manager.ts` with OAuthFlowManager class
    - Define AuthResult, TokenResponse, and OAuthError interfaces
    - Implement `initiateFlow()` to construct authorization URL
    - Generate state parameter using crypto.randomUUID()
    - Include all required OAuth parameters
    - Implement `handleCallback(params)` to validate state and extract code
    - Implement `exchangeCodeForToken(code, verifier)` to call token endpoint
    - Handle OAuth errors from callback and token endpoint
    - _Requirements: 2.5, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 6.2 Write property test for state parameter uniqueness
    - **Property 3: State Parameter Uniqueness**
    - **Validates: Requirements 2.5**

  - [ ]* 6.3 Write property test for state validation
    - **Property 4: State Validation**
    - **Validates: Requirements 4.3, 4.4**

  - [ ]* 6.4 Write property test for authorization URL construction
    - **Property 5: Authorization URL Construction**
    - **Validates: Requirements 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8**

  - [ ]* 6.5 Write property test for token exchange request correctness
    - **Property 6: Token Exchange Request Correctness**
    - **Validates: Requirements 5.2, 5.3, 5.4, 5.5, 5.6**

  - [ ]* 6.6 Write unit tests for OAuth Flow Manager
    - Test authorization URL includes all required parameters
    - Test state parameter is validated on callback
    - Test invalid state triggers error
    - Test missing state triggers error
    - Test OAuth error in callback is extracted
    - Test token exchange includes all required parameters
    - Test token exchange success returns access token
    - Test token exchange failure returns error
    - _Requirements: 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_

- [ ] 7. Implement Token Server Client
  - [ ] 7.1 Create `src/token-server-client.ts` with TokenServerClient class
    - Define ValidationResult interface
    - Implement `validateToken(accessToken)` to call Token Server
    - Send GET request to /1.0/sync/1.5 with Bearer token
    - Handle 200 success response
    - Handle 401 unauthorized error
    - Handle 503 service unavailable error
    - Handle network errors
    - Return Token Server URI from configuration
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 7.2 Write property test for Token Server URI display
    - **Property 10: Token Server URI Display**
    - **Validates: Requirements 7.3, 7.4**

  - [ ]* 7.3 Write unit tests for Token Server Client
    - Test successful validation returns Token Server URI
    - Test 401 error is handled with appropriate message
    - Test 503 error is handled with appropriate message
    - Test network errors are handled
    - Test Bearer token is included in Authorization header
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 8. Checkpoint - Ensure all core component tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement UI Controller
  - [ ] 9.1 Create `src/ui-controller.ts` with UIController class
    - Implement `showLandingPage()` to render initial state
    - Implement `showLoadingState(message)` to display loading indicator
    - Implement `showSuccessPage(tokenServerUri)` to display success and instructions
    - Implement `showErrorPage(error, details)` to display error messages
    - Implement `copyToClipboard(text)` using Clipboard API with fallback
    - Add event listeners for buttons (authenticate, restart, copy)
    - Use TypeScript DOM types for type safety
    - _Requirements: 1.1, 1.2, 1.3, 7.1, 7.2, 7.3, 7.4, 7.5, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 16.1, 16.2, 16.3, 16.4, 16.5_

  - [ ]* 9.2 Write property test for clipboard copy success
    - **Property 11: Clipboard Copy Success**
    - **Validates: Requirements 8.2**

  - [ ]* 9.3 Write unit tests for UI Controller
    - Test landing page renders with authenticate button
    - Test loading state displays indicator
    - Test success page displays Token Server URI
    - Test success page displays instructions
    - Test error page displays error message
    - Test copy to clipboard works with Clipboard API
    - Test copy to clipboard fallback works
    - _Requirements: 1.1, 1.2, 7.1, 7.3, 8.2, 13.1, 16.1, 16.5_

- [ ] 10. Implement Application Controller
  - [ ] 10.1 Create `src/application.ts` with Application class
    - Implement `initialize()` to load config and discover OIDC endpoints
    - Implement `startAuthentication()` to initiate OAuth flow
    - Implement `handleOAuthCallback()` to process callback and validate
    - Implement `restart()` to clear session and reset to initial state
    - Wire all components together with proper TypeScript types
    - Handle errors at each step
    - _Requirements: 1.4, 10.1, 10.2, 10.3, 10.4, 10.5, 13.1, 13.2, 13.3, 13.4, 13.5_

  - [ ]* 10.2 Write property test for session cleanup
    - **Property 12: Session Cleanup**
    - **Validates: Requirements 17.2, 17.4, 17.5**

  - [ ]* 10.3 Write property test for error state handling
    - **Property 13: Error State Handling**
    - **Validates: Requirements 13.1, 13.4**

  - [ ]* 10.4 Write integration test for full OAuth flow
    - Mock OIDC provider endpoints
    - Mock Token Server endpoint
    - Simulate complete flow from start to success
    - Verify Token Server URI is displayed
    - _Requirements: All_

  - [ ]* 10.5 Write integration test for error flows
    - Test OAuth error callback
    - Test token exchange failure
    - Test Token Server 401 error
    - Test Token Server 503 error
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [ ] 11. Create HTML and CSS
  - [ ] 11.1 Create `src/index.html` with semantic markup
    - Add landing page section with authenticate button
    - Add loading state section with spinner
    - Add success page section with Token Server URI and instructions
    - Add error page section with error message and restart button
    - Include script tag for bundled JavaScript
    - _Requirements: 1.1, 1.2, 7.1, 7.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 13.1, 13.4_

  - [ ] 11.2 Create `src/styles.css` with responsive design
    - Implement mobile-first responsive layout
    - Style landing page with clear call-to-action
    - Style success page with prominent Token Server URI
    - Style error page with clear error messages
    - Use monospace font for Token Server URI
    - Add loading spinner animation
    - Ensure buttons are easily tappable on mobile
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 20.1, 20.2, 20.3, 20.4, 20.5_

- [ ] 12. Implement browser compatibility checks
  - [ ] 12.1 Create `src/browser-check.ts` with compatibility checks
    - Check for Web Crypto API availability
    - Check for Fetch API availability
    - Check for sessionStorage availability
    - Display warning if required APIs are missing
    - Prevent authentication if critical APIs are missing
    - Export type-safe compatibility check results
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6_

  - [ ]* 12.2 Write property test for browser API availability
    - **Property 14: Browser API Availability**
    - **Validates: Requirements 18.2, 18.3, 18.4**

  - [ ]* 12.3 Write unit tests for browser compatibility checks
    - Test warning displayed when Crypto API missing
    - Test warning displayed when Fetch API missing
    - Test warning displayed when sessionStorage missing
    - Test no warning when all APIs available
    - _Requirements: 18.2, 18.3, 18.4, 18.5_

- [ ] 13. Create main entry point and build configuration
  - [ ] 13.1 Create `src/main.ts` as application entry point
    - Import all components
    - Initialize Application on DOMContentLoaded
    - Handle unhandled errors
    - Log errors to console
    - Export types for external use if needed
    - _Requirements: All_

  - [ ] 13.2 Create build configuration with esbuild
    - Configure esbuild to bundle TypeScript
    - Set up source maps for debugging
    - Configure minification for production
    - Copy static assets (HTML, CSS, config.example.json) to dist/
    - Create build script in package.json
    - Create dev script with watch mode
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

  - [ ] 13.3 Create `config.example.json` with sample configuration
    - Include all required fields with example values
    - Add comments explaining each field
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.6_

- [ ] 14. Checkpoint - Ensure all tests pass and application builds
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Implement CDK infrastructure stack
  - [ ] 15.1 Create `lib/stacks/auth-frontend.ts` with AuthFrontendStack
    - Create S3 bucket for static website hosting
    - Configure bucket for public read access
    - Create CloudFront distribution with S3 origin
    - Configure HTTPS redirect
    - Configure SPA routing (404 → index.html)
    - Create BucketDeployment to deploy files from auth-frontend/dist
    - Add CloudFront URL as stack output
    - _Requirements: 14.4, 14.5_

  - [ ] 15.2 Update `lib/app.ts` to include AuthFrontendStack
    - Import AuthFrontendStack
    - Instantiate stack with appropriate configuration
    - _Requirements: 14.4_

  - [ ] 15.3 Create `lib/config/auth-frontend.ts` for stack configuration
    - Define configuration interface
    - Export configuration for different environments (dev, prod)
    - _Requirements: 14.4_

- [ ] 16. Create deployment documentation
  - [ ] 16.1 Create `auth-frontend/README.md` with setup instructions
    - Document how to configure config.json
    - Document how to build the application
    - Document how to deploy with CDK
    - Document how to test locally
    - Include troubleshooting section
    - _Requirements: All_

  - [ ] 16.2 Update root README.md to mention auth frontend
    - Add section describing the auth frontend
    - Link to auth-frontend/README.md
    - _Requirements: All_

- [ ] 17. Final integration testing
  - [ ]* 17.1 Test with real Authentik instance
    - Configure config.json with real Authentik URL
    - Test complete OAuth flow
    - Verify Token Server URI is displayed correctly
    - Test Firefox configuration instructions
    - _Requirements: All_

  - [ ]* 17.2 Test responsive design on multiple devices
    - Test on desktop browsers (Chrome, Firefox, Safari, Edge)
    - Test on mobile browsers (iOS Safari, Android Chrome)
    - Verify layout adapts correctly
    - Verify buttons are easily tappable
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [ ]* 17.3 Test error scenarios
    - Test with invalid configuration
    - Test with unreachable OIDC provider
    - Test with unreachable Token Server
    - Test OAuth error callback
    - Test token exchange failure
    - Verify error messages are clear
    - Verify restart button works
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5_

- [ ] 18. Final checkpoint - Deploy and verify
  - Deploy to AWS using CDK
  - Verify CloudFront URL is accessible
  - Test complete flow in production environment
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties
- Unit tests validate specific examples and edge cases
- Integration tests validate end-to-end flows
- The implementation follows a bottom-up approach: utilities → components → integration → infrastructure
