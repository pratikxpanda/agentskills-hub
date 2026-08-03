import { useCallback, useEffect, useState } from "react";

/**
 * Four pages and one parameter do not need a routing library. This one exists so the address bar
 * and the back button work, and stops there.
 */
export type Route =
  | { name: "catalog" }
  | { name: "skill"; skillId: string }
  | { name: "subscriptions" }
  | { name: "publish" };

export function parse(pathname: string): Route {
  const segments = pathname.split("/").filter(Boolean);
  if (segments[0] === "skills" && segments[1]) {
    return { name: "skill", skillId: decodeURIComponent(segments[1]) };
  }
  if (segments[0] === "subscriptions") return { name: "subscriptions" };
  if (segments[0] === "publish") return { name: "publish" };
  return { name: "catalog" };
}

export function href(route: Route): string {
  switch (route.name) {
    case "skill":
      return `/skills/${encodeURIComponent(route.skillId)}`;
    case "subscriptions":
      return "/subscriptions";
    case "publish":
      return "/publish";
    case "catalog":
      return "/";
  }
}

export function useRoute(): [Route, (route: Route) => void] {
  const [route, setRoute] = useState(() => parse(window.location.pathname));

  useEffect(() => {
    const onPop = () => setRoute(parse(window.location.pathname));
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback((next: Route) => {
    window.history.pushState(null, "", href(next));
    setRoute(next);
  }, []);

  return [route, navigate];
}
