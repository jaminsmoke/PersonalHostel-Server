import { afterEach, describe, expect, it, vi } from "vitest";
import { enviarPedidoMesa, resolverMesa } from "./api";
import { API_BASE } from "./config";
import { CARTA_DEMO } from "./mesa";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("resolverMesa", () => {
  it("el token demo no llama a la API y usa el catálogo local", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    const mesa = await resolverMesa("demo");
    expect(mesa.modo).toBe("demo");
    expect(mesa.carta).toEqual(CARTA_DEMO);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("404 → invalido", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 404 })),
    );
    await expect(resolverMesa("token-inexistente")).rejects.toEqual({
      tipo: "invalido",
    });
  });

  it("410 → revocado", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 410 })),
    );
    await expect(resolverMesa("token-rotado")).rejects.toEqual({
      tipo: "revocado",
    });
  });
});

describe("enviarPedidoMesa", () => {
  const linea = {
    productoId: "cafe-leche",
    nombre: "Café con leche",
    cantidad: 1,
    precio_centimos: 150,
  };

  it("409 → cerrado", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(new Response("{}", { status: 409 }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(enviarPedidoMesa("mesa-token", [linea])).rejects.toEqual({
      tipo: "cerrado",
    });
    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { method: string },
    ];
    expect(url).toBe(`${API_BASE}/v1/cfc/mesa/mesa-token/pedidos`);
    expect(init.method).toBe("POST");
  });

  it("429 → limite", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 429 })),
    );
    await expect(enviarPedidoMesa("mesa-token", [linea])).rejects.toEqual({
      tipo: "limite",
    });
  });
});
