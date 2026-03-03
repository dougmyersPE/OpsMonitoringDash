import axios from "axios";

const apiClient = axios.create({ baseURL: "/api/v1" });

export default apiClient;
