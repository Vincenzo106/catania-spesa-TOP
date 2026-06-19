import { Platform } from "react-native";

const DEFAULT_API_BASE_URL =
  process.env.EXPO_PUBLIC_API_BASE_URL ||
  (Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://127.0.0.1:8000");

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
  const response = await fetch(`${DEFAULT_API_BASE_URL}${path}${query}`);

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Ignore JSON parsing issues and surface the generic fallback.
    }
    throw new Error(detail);
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

export const API_BASE_URL = DEFAULT_API_BASE_URL;
