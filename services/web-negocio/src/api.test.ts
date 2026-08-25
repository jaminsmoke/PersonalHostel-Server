import { afterEach, describe, expect, it, vi } from "vitest";
import { cargarWeb, ErrorPublico } from "./api";
import { API_BASE } from "./config";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function jsonResponse(
  status: number,
  body: unknown,
  headers: Record<string, string> = {},
): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

const webMinima = {
  establecimiento_id: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  nombre: "La Terraza",
  organizacion_nombre: "Org",
  plantilla: "estate",
  galeria: [],
  equipo: [],
  categorias: [],
};

describe("cargarWeb", () => {
  it("devuelve el JSON y el ETag en 200", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(200, webMinima, { ETag: '"rev-1"' }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const out = await cargarWeb("terraza");
    expect(out).toEqual({ web: webMinima, etag: '"rev-1"' });
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [
      string,
      { headers: Record<string, string> },
    ];
    expect(url).toBe(`${API_BASE}/v1/negocio/web?slug=terraza`);
    expect(init.headers.Accept).toBe("application/json");
    expect(init.headers["If-None-Match"]).toBeUndefined();
  });

  it("devuelve null en 304 y envía If-None-Match", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 304 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(cargarWeb("terraza", '"rev-1"')).resolves.toBeNull();
    const [, init] = fetchMock.mock.calls[0] as [
      string,
      { headers: Record<string, string> },
    ];
    expect(init.headers["If-None-Match"]).toBe('"rev-1"');
  });

  it("lanza ErrorPublico en 410 identity.web_privada", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse(410, {
          code: "identity.web_privada",
          detail: "La web de este establecimiento no es pública.",
        }),
      ),
    );

    try {
      await cargarWeb("privado");
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ErrorPublico);
      const pub = err as ErrorPublico;
      expect(pub.status).toBe(410);
      expect(pub.code).toBe("identity.web_privada");
    }
  });
});
