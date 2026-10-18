import { useEffect, useState } from "react";
import type { ChangelogData } from "./changelog";

/** Načte `changelog.json` — statický soubor z buildu web image
 * (generuje frontend-web/scripts/gen-changelog.mjs; host dev servíruje stub). */
export function useChangelog(): { data: ChangelogData | null; error: boolean } {
  const [data, setData] = useState<ChangelogData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch("/changelog.json")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then(setData)
      .catch(() => setError(true));
  }, []);

  return { data, error };
}
