import { describe, expect, it } from "vitest";
import { rutaNegocio } from "./web-context";

describe("rutaNegocio", () => {
  it("compone la ruta canónica del local y de cada sección", () => {
    expect(rutaNegocio("terraza")).toBe("/negocios/terraza");
    expect(rutaNegocio("terraza", "carta")).toBe("/negocios/terraza/carta");
    expect(rutaNegocio("terraza", "horario")).toBe("/negocios/terraza/horario");
  });
});
