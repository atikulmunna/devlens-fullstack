"use client";

import { usePathname } from "next/navigation";
import { createContext, ReactNode, useCallback, useContext, useEffect, useState } from "react";
import { LoadingPill } from "@/components/loading";
import { CurrentUser, loadCurrentUser, signInHref, signOut } from "@/lib/auth";

type AuthState = {
  status: "loading" | "signed-in" | "signed-out";
  user: CurrentUser | null;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

// Loads the session once (refresh cookie -> access token -> /auth/me) and shares it, so the header
// and pages never race each other into concurrent refreshes.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>("loading");

  useEffect(() => {
    let cancelled = false;
    loadCurrentUser()
      .then((current) => {
        if (!cancelled) {
          setUser(current);
          setStatus(current ? "signed-in" : "signed-out");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus("signed-out");
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSignOut = useCallback(async () => {
    try {
      await signOut();
    } finally {
      setUser(null);
      setStatus("signed-out");
    }
  }, []);

  return <AuthContext.Provider value={{ status, user, signOut: handleSignOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}

// Sign-in link that brings the user back to the page they started from (path and query).
export function SignInLink({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [here, setHere] = useState("/workspace");

  useEffect(() => {
    setHere(window.location.pathname + window.location.search);
  }, [pathname]);

  return <a href={signInHref(here)}>{children}</a>;
}

export function AuthStatus() {
  const { status, user, signOut: handleSignOut } = useAuth();

  if (status === "loading") {
    return <LoadingPill label="Checking sign-in" />;
  }
  if (!user) {
    return <SignInLink>Sign in with GitHub</SignInLink>;
  }
  return (
    <span className="row">
      {user.avatar_url && (
        // A 24px GitHub avatar does not need the Next image optimizer (or its remote-host config).
        // eslint-disable-next-line @next/next/no-img-element
        <img src={user.avatar_url} alt="" width={24} height={24} className="avatar" />
      )}
      <span>{user.username}</span>
      <button type="button" className="button secondary" onClick={() => void handleSignOut()}>
        Sign out
      </button>
    </span>
  );
}
