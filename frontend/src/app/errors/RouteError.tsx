// Route error boundary (X:route-error; SCREENS §0.4 placement row; SCREENS_B §12.4; PRD ERR-34, CPY-05).
// An unhandled render or loader error replaces the page inside the shell with the heading "Something
// went wrong", a sentence that nothing was saved with a reference, and the actions "Reload page",
// "Go to Home" and "Copy reference". No stack trace, SQL or internal detail is shown. Focus moves to
// the heading, which is announced assertively once. A 404 route response renders X:not-found.
import { useEffect, useRef, useState } from "react";
import { isRouteErrorResponse, useNavigate, useRouteError } from "react-router";

import { CopySimple } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { announce } from "../../lib/a11y/announce";
import { ApiProblem } from "../../lib/api/problems";
import { t } from "../../lib/i18n/t";
import { NotFound, type NotFoundProps } from "./NotFound";

/**
 * The reference of an error: the request id of an API problem. An error that carries none, such as a
 * render error, gets a generated reference (L1-4-Q-10).
 */
export function errorReference(error: unknown): string {
  if (error instanceof ApiProblem && error.requestId !== null) {
    return error.requestId;
  }
  return crypto.randomUUID();
}

export function RouteError({ homePath }: NotFoundProps) {
  const error = useRouteError();
  if (isRouteErrorResponse(error) && error.status === 404) {
    return <NotFound homePath={homePath} />;
  }
  return <ErrorPage error={error} homePath={homePath} />;
}

interface ErrorPageProps extends NotFoundProps {
  readonly error: unknown;
}

function ErrorPage({ error, homePath }: ErrorPageProps) {
  const navigate = useNavigate();
  const heading = useRef<HTMLHeadingElement>(null);
  const announced = useRef(false);
  const [reference] = useState(() => errorReference(error));
  const title = t("errors.routeError.title");

  useEffect(() => {
    heading.current?.focus();
    if (!announced.current) {
      announced.current = true;
      announce(title, "assertive");
    }
  }, [title]);

  const copyReference = () => {
    const clipboard = navigator.clipboard as Clipboard | undefined;
    if (clipboard === undefined) {
      return;
    }
    void clipboard.writeText(reference).then(
      () => announce(t("errors.routeError.copied")),
      () => undefined,
    );
  };

  return (
    <div
      data-testid="X-page"
      className="flex max-w-[var(--content-max-form)] flex-col items-start gap-2 pt-12"
    >
      <h1 ref={heading} tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      <p data-testid="X-banner-route-error" data-volatile="true" className="text-body text-fg-2">
        {t("errors.routeError.body", { reference })}
      </p>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={() => window.location.reload()}>
          {t("errors.routeError.reload")}
        </Button>
        <Button onClick={() => void navigate(homePath)}>{t("errors.routeError.goHome")}</Button>
        <Button variant="ghost" icon={CopySimple} onClick={copyReference}>
          {t("errors.routeError.copyReference")}
        </Button>
      </div>
    </div>
  );
}
