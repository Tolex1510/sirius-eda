import { useEffect, useState } from "react";
import { api, renew, signOut } from "../lib/api";
import { message } from "../lib/format";
import type { User } from "../types";

export function useSession() {
  const [user, setUser] = useState<User | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [logoutError, setLogoutError] = useState("");

  useEffect(() => {
    void renew()
      .then(async (ok) => {
        if (ok)
          try {
            setUser(await api<User>("/users/me"));
          } catch {
            setUser(null);
          }
      })
      .finally(() => setSessionReady(true));
    const expired = () => setUser(null);
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);

  async function logout() {
    try {
      await signOut();
      setUser(null);
      setLogoutError("");
      return true;
    } catch (err) {
      setLogoutError(message(err));
      return false;
    }
  }
  return { user, setUser, sessionReady, logoutError, logout };
}
