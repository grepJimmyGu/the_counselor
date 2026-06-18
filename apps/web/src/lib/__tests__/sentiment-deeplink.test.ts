import { describe, expect, it } from "vitest";
import {
  humanizeDisplayLabel,
  readSentimentDeepLink,
} from "../sentiment-deeplink";

describe("readSentimentDeepLink", () => {
  it("reads toolkit + autorun + display together", () => {
    const dl = readSentimentDeepLink(
      "?toolkit=news_community_confirmed&autorun=1&display=mainstream_buyers",
    );
    expect(dl.toolkitId).toBe("news_community_confirmed");
    expect(dl.autorun).toBe(true);
    expect(dl.displayLabel).toBe("Mainstream Buyers");
  });

  it("autorun is true only for exactly '1'", () => {
    expect(readSentimentDeepLink("?toolkit=x&autorun=true").autorun).toBe(false);
    expect(readSentimentDeepLink("?toolkit=x&autorun=0").autorun).toBe(false);
    expect(readSentimentDeepLink("?toolkit=x").autorun).toBe(false);
    expect(readSentimentDeepLink("?toolkit=x&autorun=1").autorun).toBe(true);
  });

  it("returns all-null/false when no params are present", () => {
    expect(readSentimentDeepLink("")).toEqual({
      toolkitId: null,
      autorun: false,
      displayLabel: null,
    });
  });

  it("displayLabel is null without ?display=", () => {
    expect(readSentimentDeepLink("?toolkit=x&autorun=1").displayLabel).toBeNull();
  });
});

describe("humanizeDisplayLabel", () => {
  it("title-cases snake_case and kebab-case", () => {
    expect(humanizeDisplayLabel("mainstream_buyers")).toBe("Mainstream Buyers");
    expect(humanizeDisplayLabel("rising-attention")).toBe("Rising Attention");
    expect(humanizeDisplayLabel("catalyst")).toBe("Catalyst");
  });
});
