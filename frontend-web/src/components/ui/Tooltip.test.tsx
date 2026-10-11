import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Tooltip } from "./Tooltip";

describe("Tooltip", () => {
  it("zobrazí content pouze při hoveru", () => {
    render(
      <Tooltip content="První kolo jednání" testId="tip">
        <span className="w-2.5 h-5 bg-emerald-500" />
      </Tooltip>,
    );
    expect(screen.queryByRole("tooltip")).toBeNull();

    fireEvent.mouseEnter(screen.getByTestId("tip"));
    expect(screen.getByRole("tooltip").textContent).toBe("První kolo jednání");

    fireEvent.mouseLeave(screen.getByTestId("tip"));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("zobrazí tooltip při fokusu a skryje při blur (klávesnice)", () => {
    render(
      <Tooltip content="Fokus content" testId="tip">
        <a href="/x">odkaz</a>
      </Tooltip>,
    );
    // React onFocus/onBlur je postavený na focusin/focusout (bublují) –
    // jako při skutečném focusu v prohlížeči.
    const link = screen.getByRole("link");
    expect(screen.queryByRole("tooltip")).toBeNull();
    fireEvent.focusIn(link);
    expect(screen.getByRole("tooltip").textContent).toBe("Fokus content");
    fireEvent.focusOut(link);
    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});
