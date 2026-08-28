import axios from "axios";

const baseURL = (import.meta.env.VITE_API_URL as string | undefined) || "/api/v1";

const client = axios.create({
  baseURL,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("token");
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // optional: do not auto-clear on public endpoints; just reject
    }
    return Promise.reject(error);
  },
);

export default client;

// unauthenticated client for public preview without auto-attaching token
export const publicClient = axios.create({
  baseURL,
});
