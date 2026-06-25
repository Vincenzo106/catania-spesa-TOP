const API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL || "https://catania-spesa-top.onrender.com";

function buildQuery(params = {}) {
  const searchParams = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      searchParams.set(key, String(value));
    }
  });
  return searchParams.toString();
}

async function request(path, params) {
  const query = params ? `?${buildQuery(params)}` : "";
  const requestUrl = `${API_BASE_URL}${path}${query}`;
  const response = await fetch(requestUrl, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!response.ok) {
    let detail = `Non riesco a raggiungere il server delle offerte (${response.status}).`;

    try {
      const body = await response.json();
      detail = body.detail || body.message || detail;
    } catch {
      // Manteniamo il messaggio di fallback se la risposta non e JSON.
    }

    const error = new Error(detail);
    error.httpStatus = response.status;
    error.requestUrl = requestUrl;
    throw error;
  }

  return response.json();
}

export async function fetchStores() {
  return request("/stores");
}

export async function fetchOffers({ store, category, limit = 100 }) {
  return request("/offers", { store, category, limit });
}

export async function fetchBestDeals({ store, category, limit = 8 }) {
  return request("/offers/best", { store, category, limit });
}

export async function fetchMetadata() {
  return request("/metadata");
}

export { API_BASE_URL };
