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
});
