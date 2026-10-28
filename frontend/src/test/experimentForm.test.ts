import { describe, expect, it } from "vitest";
import type { Capabilities } from "../api/types";
import { buildConfig, engineTokens, initialForm, validate, type FormState } from "../lib/experimentForm";
import capsJson from "./fixtures/capabilities.json";

const limits = (capsJson as Capabilities).limits;
const form = (patch: Partial<FormState>): FormState => ({ ...initialForm, ...patch });

describe("workbench validation", () => {
  it("accepts the default comparison", () => {
    expect(validate(initialForm, limits)).toEqual({});
  });

  it("rejects image sizes outside the engine limits", () => {
    expect(validate(form({ width: 5 }), limits).width).toMatch(/16 to 8192/);
    expect(validate(form({ height: "" }), limits).height).toBeDefined();
    expect(validate(form({ width: 8192, height: 8192 }), limits)).toEqual({});
  });

  it("rejects tiles larger than the image and non-positive tiles", () => {
    expect(validate(form({ width: 64, height: 64, compareTiles: [{ w: 128, h: 8 }] }), limits).strategies).toMatch(/larger than/);
    expect(validate(form({ mode: "single", single: "tiled", singleTile: { w: 0, h: 8 } }), limits).tile).toBeDefined();
  });

  it("requires two strategies for a comparison", () => {
    const e = validate(form({ compare: ["morton"], compareTiles: [] }), limits);
    expect(e.strategies).toMatch(/at least two/);
  });

  it("requires an uploaded file for the upload source", () => {
    expect(validate(form({ imageSource: "upload", upload: null }), limits).upload).toBeDefined();
  });

  it("checks custom cache geometry like the backend", () => {
    const base = form({ cacheSim: true, customGeometry: true, width: 512, height: 512 });
    expect(validate(base, limits)).toEqual({});
    expect(validate({ ...base, l1: { kib: 48, ways: 7 } }, limits).l1).toMatch(/whole number of sets/);
    expect(validate({ ...base, l2: { kib: 1024, ways: "" } }, limits).l2).toBeDefined();
  });

  it("refuses cache simulation above the simulator limit", () => {
    expect(validate(form({ cacheSim: true, width: 8192, height: 8192 }), limits).cacheSim).toBeDefined();
  });
});

describe("request building", () => {
  it("adds the row-major baseline to comparisons, exactly like the backend", () => {
    expect(engineTokens(form({ compare: ["morton"], compareTiles: [{ w: 32, h: 32 }] }))).toEqual(["row_major", "morton", "tiled:32x32"]);
    expect(engineTokens(form({ mode: "single", single: "morton" }))).toEqual(["morton"]);
  });

  it("omits width/height for uploads and only sends tile sizes for tiled strategies", () => {
    const cfg = buildConfig(
      form({
        imageSource: "upload",
        upload: { upload_id: "abcdefabcdef", width: 100, height: 50, sha256: "x", original_name: "a.png", bytes: 1 },
        compare: ["row_major"],
        compareTiles: [{ w: 16, h: 16 }],
      }),
    );
    expect(cfg.width).toBeNull();
    expect(cfg.upload_id).toBe("abcdefabcdef");
    expect(cfg.strategies).toEqual([{ strategy: "row_major" }, { strategy: "tiled", tile_w: 16, tile_h: 16 }]);
    expect(cfg.cache_sim).toEqual({ enabled: false });
  });
});
