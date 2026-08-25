if (typeof globalThis.window === "undefined") {
  Object.defineProperty(globalThis, "window", {
    value: { NEGOCIO_API_URL: "http://negocio.test" },
    writable: true,
  });
}
