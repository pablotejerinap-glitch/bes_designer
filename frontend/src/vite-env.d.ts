/// <reference types="vite/client" />

/**
 * Variables de entorno del build.
 *
 * Se declaran para que TypeScript las conozca: sin esto `import.meta.env`
 * devuelve `any` y un error de tipeo en el nombre de la variable no lo detecta
 * nadie hasta que la app no encuentra el backend en producción.
 */
interface ImportMetaEnv {
  /**
   * URL pública del backend, sin barra final (ej. `https://api.ejemplo.com`).
   *
   * Vacía o ausente significa **mismo origen**, que es lo que vale en dev
   * —Vite proxya `/api` al :8000— y detrás de nginx en docker-compose. En
   * Netlify el backend vive en otro dominio y hay que cargarla.
   */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
