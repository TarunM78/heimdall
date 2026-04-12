/**
 * AUTH0 HELPER
 * Wraps the Auth0 SPA SDK for Heimdall.
 */

let auth0Client = null;

/**
 * Initialize Auth0 client by fetching config from the backend.
 */
async function initAuth() {
    try {
        const response = await fetch('/api/auth/config');
        const config = await response.json();

        auth0Client = await auth0.createAuth0Client({
            domain: config.domain,
            clientId: config.clientId,
            authorizationParams: {
                redirect_uri: window.location.origin
            },
            cacheLocation: 'localstorage', // Ensures session persists on refresh
            useRefreshTokens: true
        });

        // Handle callback if returning from Auth0
        if (window.location.search.includes("code=") && window.location.search.includes("state=")) {
            await auth0Client.handleRedirectCallback();
            window.history.replaceState({}, document.title, window.location.pathname);
        }

        return auth0Client;
    } catch (e) {
        console.error("Auth0 initialization failed", e);
        return null;
    }
}

async function login() {
    console.log("Login clicked, client:", !!auth0Client);
    if (!auth0Client) {
        alert("Auth0 client not initialized yet.");
        return;
    }
    await auth0Client.loginWithRedirect();
}

async function logout() {
    if (!auth0Client) return;
    await auth0Client.logout({
        logoutParams: {
            returnTo: window.location.origin
        }
    });
}

async function getToken() {
    if (!auth0Client) return null;
    try {
        const claims = await auth0Client.getIdTokenClaims();
        return claims.__raw; // Use raw ID Token (JWT) since no audience is configured
    } catch (e) {
        return null;
    }
}

async function getUser() {
    if (!auth0Client) return null;
    return await auth0Client.getUser();
}

async function isAuthenticated() {
    if (!auth0Client) return false;
    return await auth0Client.isAuthenticated();
}
