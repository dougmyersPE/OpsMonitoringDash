import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface AuthState {
  token: string | null;
  email: string | null;
  role: string | null;
  rememberMe: boolean;
  login: (token: string, email: string, role: string, rememberMe: boolean) => void;
  logout: () => void;
}

// Routes reads/writes to localStorage or sessionStorage based on the rememberMe
// flag stored in the state. Falls back to localStorage for existing sessions.
const rememberMeStorage = {
  getItem: (name: string) =>
    localStorage.getItem(name) ?? sessionStorage.getItem(name),
  setItem: (name: string, value: string) => {
    try {
      const rememberMe = (JSON.parse(value) as { state?: { rememberMe?: boolean } })
        ?.state?.rememberMe ?? true;
      if (rememberMe) {
        localStorage.setItem(name, value);
        sessionStorage.removeItem(name);
      } else {
        sessionStorage.setItem(name, value);
        localStorage.removeItem(name);
      }
    } catch {
      localStorage.setItem(name, value);
    }
  },
  removeItem: (name: string) => {
    localStorage.removeItem(name);
    sessionStorage.removeItem(name);
  },
};

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      email: null,
      role: null,
      rememberMe: true,
      login: (token, email, role, rememberMe) =>
        set({ token, email, role, rememberMe }),
      logout: () => set({ token: null, email: null, role: null, rememberMe: true }),
    }),
    {
      name: "prophet-auth",
      storage: createJSONStorage(() => rememberMeStorage),
    }
  )
);
