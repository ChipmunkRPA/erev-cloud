// The router's own search (docs/dev-guide.md DG-FE-03 rev 1.215). A component renders an address a
// moment after the router takes it, so a control that works out its next write from the search it
// last rendered undoes the write before it. `useLiveSearch` answers a function that reads what the
// router holds when it is called: the search of a navigation on its way to the path on screen, else
// the search of the address the router is at. Under a router that keeps no such state (a component
// test's `MemoryRouter`) it answers the search last rendered. `useLivePath` answers the path the
// router is at in the same way: a command awaited on one record's page asks it before and after, to
// see whether that page is still the one on screen (RPT-VIEWER-LATE-RUN-1). `usePageStays` answers
// that question whole for a write that names its own path, which the router's guard does not see
// (rule (3), rev 1.230): the component is mounted, the router is at the path it rendered for, and no
// navigation to another path is on its way.
import { useCallback, useContext, useEffect, useRef } from "react";
import { type DataRouter, UNSAFE_DataRouterContext, useLocation } from "react-router";

export function liveSearch(router: DataRouter): string {
  const { location, navigation } = router.state;
  return navigation.location?.pathname === location.pathname
    ? navigation.location.search
    : location.search;
}

export function useLiveSearch(): () => string {
  const router = useContext(UNSAFE_DataRouterContext)?.router;
  const { search } = useLocation();
  const rendered = useRef(search);
  useEffect(() => {
    rendered.current = search;
  });
  return useCallback(
    () => (router === undefined ? rendered.current : liveSearch(router)),
    [router],
  );
}

export function usePageStays(): () => boolean {
  const router = useContext(UNSAFE_DataRouterContext)?.router;
  const { pathname } = useLocation();
  const rendered = useRef(pathname);
  const mounted = useRef(false);
  useEffect(() => {
    rendered.current = pathname;
  });
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  return useCallback(() => {
    if (!mounted.current) {
      return false;
    }
    if (router === undefined) {
      return true;
    }
    const { location, navigation } = router.state;
    return (
      location.pathname === rendered.current &&
      (navigation.location === undefined || navigation.location.pathname === location.pathname)
    );
  }, [router]);
}

export function useLivePath(): () => string {
  const router = useContext(UNSAFE_DataRouterContext)?.router;
  const { pathname } = useLocation();
  const rendered = useRef(pathname);
  useEffect(() => {
    rendered.current = pathname;
  });
  return useCallback(
    () => (router === undefined ? rendered.current : router.state.location.pathname),
    [router],
  );
}
