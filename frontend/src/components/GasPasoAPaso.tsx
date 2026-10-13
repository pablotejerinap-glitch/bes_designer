// Método nuevo de gas, paso a paso (bes.core.gas_paso_a_paso).
// Muestra las cuentas de cada paso y la evolución del fluido como una planilla.
import { useEffect, useRef, useState } from "react";
import { Accordion, Alert, Button, Card, Group, NumberInput, ScrollArea, Table, Text, Title } from "@mantine/core";
import { api, ApiError, openHtmlInNewTab } from "../api/client";
import type { DesignInputs } from "../api/types";

type Paso = { nombre: string; formula: string; sustitucion: string; valor: number | null; unidad: string; cita: string };
type Fila = {
  zona: string; comentario: string; p: number; t: number; gor: number; z: number; rs: number;
  bg_mscf: number; bo: number; bw: number; vg: number; v_total: number; sg: number;
};
type Escalon = {
  p0: number; p1: number; dp: number; q: number; grad: number; sg: number; altura: number;
  h: number; hp_et: number; psi_et: number; n: number; hp: number;
};
export type PasoAPasoResponse = {
  bloques: { titulo: string; pasos: Paso[] }[];
  tabla_evolucion: Fila[];
  escalones: Escalon[];
  resumen: Record<string, number | string | null> & {
    carcasas?: { carcasa: string; etapas: number; cantidad: number; largo_ft: number }[] | null;
    motor_arreglo?: string[] | null;
  };
};

const fmt = (v: number, d: number) =>
  v.toLocaleString("es-AR", { minimumFractionDigits: d, maximumFractionDigits: d });

// Aspecto de planilla: bordes en todas las celdas, números alineados a la
// derecha, encabezado fijo y una columna con el número de fila.
const celda = { fontFamily: "Consolas, 'Courier New', monospace", fontSize: 12, textAlign: "right" as const };
const encabezado = { background: "#e9ecef", fontSize: 12, whiteSpace: "nowrap" as const };
const colorZona: Record<string, string> = {
  fondo: "#fff4e6", admision: "#fff4e6", bomba: "#e7f5ff", tubing: "#ffffff",
};

function Planilla({ columnas, filas, colores }: {
  columnas: string[]; filas: (string | number)[][]; colores?: string[];
}) {
  return (
    <ScrollArea h={Math.min(38 * (filas.length + 1), 560)} type="auto">
      <Table withTableBorder withColumnBorders stickyHeader highlightOnHover verticalSpacing={2}>
        <Table.Thead>
          <Table.Tr>
            <Table.Th style={encabezado}>#</Table.Th>
            {columnas.map((c) => <Table.Th key={c} style={encabezado}>{c}</Table.Th>)}
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {filas.map((f, i) => (
            <Table.Tr key={i} style={{ background: colores?.[i] }}>
              <Table.Td style={{ ...celda, background: "#f1f3f5", color: "#868e96" }}>{i + 1}</Table.Td>
              {f.map((v, j) => (
                <Table.Td key={j} style={typeof v === "string" ? { ...celda, textAlign: "left" } : celda}>
                  {v}
                </Table.Td>
              ))}
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </ScrollArea>
  );
}

export function GasPasoAPaso({ inputs, autoRunToken = 0 }: { inputs: DesignInputs | null; autoRunToken?: number }) {
  const [incrementoPsi, setIncrementoPsi] = useState<number>(200);
  const yaDisparado = useRef(0);
  const [eta, setEta] = useState<number>(75);
  const [res, setRes] = useState<PasoAPasoResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(false);
  const [abriendo, setAbriendo] = useState(false);

  async function verMemoria() {
    if (!inputs) return;
    setAbriendo(true);
    setError(null);
    try {
      await openHtmlInNewTab(() => api.gasMemoria({ ...inputs, increment_psi: incrementoPsi,
                                                     eta_separador: eta / 100, titulo: "Pozo con gas" }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setAbriendo(false);
    }
  }

  async function calcular() {
    if (!inputs) return;
    setCargando(true);
    setError(null);
    setRes(null);
    try {
      setRes(await api.gasPasoAPaso({ ...inputs, increment_psi: incrementoPsi, eta_separador: eta / 100 }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setCargando(false);
    }
  }

  // "Ir a Pozo con gas" desde Diseño: corre el método solo.
  useEffect(() => {
    if (autoRunToken > 0 && autoRunToken !== yaDisparado.current && inputs) {
      yaDisparado.current = autoRunToken;
      void calcular();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRunToken]);

  const r = res?.resumen;
  return (
    <Card padding="lg">
      <Title order={4}>Método paso a paso (nuevo)</Title>
      <Group mt="sm" align="end">
        <NumberInput label="Eficiencia del separador [%]" value={eta} min={0} max={99}
                     onChange={(v) => setEta(Number(v) || 0)} w={200} />
        <NumberInput label="Escalón de presión [psi]" value={incrementoPsi} min={10} max={1000} step={25}
                     onChange={(v) => setIncrementoPsi(Number(v) || 200)} w={200} />
        <Button onClick={calcular} loading={cargando} disabled={!inputs}>Calcular paso a paso</Button>
        <Button variant="light" disabled={!inputs || !res} loading={abriendo} onClick={verMemoria}>
          Memoria de cálculo
        </Button>
      </Group>
      {error && (
        <Alert color="red" mt="sm">
          {error.startsWith("Ninguna bomba candidata completa el aparejo: ") ? (
            <>
              <Text size="sm" fw={600}>Ninguna bomba candidata completa el aparejo:</Text>
              {error.replace("Ninguna bomba candidata completa el aparejo: ", "").split(" | ").map((m, i) => (
                <Text key={i} size="sm">• {m}</Text>
              ))}
            </>
          ) : error}
        </Alert>
      )}

      {res && r && (
        <>
          <Title order={5} mt="lg">Resultado</Title>
          <Planilla
            columnas={["Magnitud", "Valor"]}
            filas={[
              ["Pwf [psig]", fmt(Number(r.pwf), 2)],
              ["PIP [psig]", fmt(Number(r.pip), 2)],
              ["T en la admisión [°F]", fmt(Number(r.t_admision), 2)],
              ["GOR en la bomba [scf/STB]", fmt(Number(r.gor_bomba), 3)],
              ["Gas libre en la bomba [%]", fmt(Number(r.gas_libre_bomba) * 100, 2)],
              ["Presión de descarga [psig]", r.p_descarga == null ? "—" : fmt(Number(r.p_descarga), 2)],
              ["Bomba", `${r.bomba} a ${fmt(Number(r.frecuencia_hz), 0)} Hz`],
              ["Etapas", r.etapas == null ? "—" : `${r.etapas} (Σ = ${fmt(Number(r.etapas_exactas), 2)})`],
              ["Potencia al eje [hp]", r.hp == null ? "—" : fmt(Number(r.hp), 2)],
              ["Eje", r.eje == null ? "—" : String(r.eje)],
              ["Presión máxima en la bomba [psi]",
               r.p_max_carcasa == null ? "—" : `${fmt(Number(r.p_max_carcasa), 0)} (carcasa ${r.carcasa})`],
              ["Carcasas", r.carcasas ? r.carcasas.map((c) =>
                `${c.cantidad} × ${c.carcasa} (${c.etapas} etapas)`).join(" + ") : "—"],
              ["Etapas ciegas", r.etapas_ciegas == null ? "—" : String(r.etapas_ciegas)],
              ["Largo de la bomba [ft]", r.largo_bomba_ft == null ? "—" : fmt(Number(r.largo_bomba_ft), 1)],
              ["Protector", r.protector == null ? "—"
                : `${r.protector} (P/N ${r.protector_pn}, ${fmt(Number(r.protector_largo_ft), 1)} ft)`],
              ["Elastómero", r.elastomero == null ? "—" : String(r.elastomero)],
              ["Serie del motor", r.serie_motor == null ? "—" : String(r.serie_motor)],
              ["Potencia del sistema [hp]", r.bhp_sistema == null ? "—" : fmt(Number(r.bhp_sistema), 2)],
              ["Motor", r.motor == null ? "—" : `${r.motor_n} × ${r.motor}`],
              ["Motor: placa", r.motor_hp == null ? "—"
                : `${fmt(Number(r.motor_hp), 1)} hp · ${fmt(Number(r.motor_voltaje), 0)} V`],
              ["Corriente del motor [A]", r.motor_corriente == null ? "—" : fmt(Number(r.motor_corriente), 2)],
              ["Velocidad junto al motor [ft/s]", r.v_anular == null ? "—" : fmt(Number(r.v_anular), 2)],
              ["Cable", r.cable == null ? "—"
                : `${r.cable} · ${fmt(Number(r.cable_largo_ft), 0)} ft · caída ${fmt(Number(r.cable_caida_v), 1)} V`],
              ["Extensión del motor (MLE) [ft]", r.mle_largo_ft == null ? "—" : fmt(Number(r.mle_largo_ft), 1)],
              ["Tensión en superficie [V]", r.u_superficie == null ? "—" : fmt(Number(r.u_superficie), 1)],
              ["Potencia en superficie [kVA]", r.kva == null ? "—" : fmt(Number(r.kva), 1)],
              ["Tablero", r.tablero == null ? "—" : String(r.tablero)],
              ["Transformador", r.transformador_kva == null ? "—"
                : `${fmt(Number(r.transformador_kva), 0)} kVA (P/N ${r.transformador_pn})`],
            ]}
          />

          <Title order={5} mt="lg">Evolución del fluido en el pozo</Title>
          <Text size="xs" c="dimmed">
            Naranja: fondo y admisión · celeste: dentro de la bomba · blanco: tubing hasta la boca.
          </Text>
          <Planilla
            columnas={["P [psig]", "T [°F]", "GOR [scf/STB]", "Z", "Rs [scf/STB]", "Bg [bbl/Mscf]",
                       "Bo [bbl/STB]", "Bw [bbl/STB]", "Vg [b/d]", "V total [b/d]", "SG mezcla", "Ubicación"]}
            filas={res.tabla_evolucion.map((f) => [
              fmt(f.p, 2), fmt(f.t, 2), fmt(f.gor, 2), fmt(f.z, 5), fmt(f.rs, 3), fmt(f.bg_mscf, 4),
              fmt(f.bo, 4), fmt(f.bw, 4), fmt(f.vg, 2), fmt(f.v_total, 2), fmt(f.sg, 4), f.comentario,
            ])}
            colores={res.tabla_evolucion.map((f) => colorZona[f.zona])}
          />

          <Title order={5} mt="lg">Escalones de presión dentro de la bomba</Title>
          <Planilla
            columnas={["P inicial", "P final", "ΔP [psi]", "q prom [b/d]", "grad [psi/ft]", "altura [ft]",
                       "H/etapa [ft]", "psi/etapa", "etapas", "hp/etapa", "SG", "hp"]}
            filas={res.escalones.map((e) => [
              fmt(e.p0, 2), fmt(e.p1, 2), fmt(e.dp, 2), fmt(e.q, 2), fmt(e.grad, 5), fmt(e.altura, 2),
              fmt(e.h, 4), fmt(e.psi_et, 4), fmt(e.n, 3), fmt(e.hp_et, 5), fmt(e.sg, 4), fmt(e.hp, 3),
            ])}
          />

          <Title order={5} mt="lg">Cuentas de cada paso</Title>
          <Accordion variant="contained" multiple>
            {res.bloques.map((b) => (
              <Accordion.Item key={b.titulo} value={b.titulo}>
                <Accordion.Control>{b.titulo}</Accordion.Control>
                <Accordion.Panel>
                  <Planilla
                    columnas={["Cuenta", "Fórmula", "Sustitución", "Resultado", "Unidad", "Fuente"]}
                    filas={b.pasos.map((p) => [p.nombre, p.formula, p.sustitucion,
                      p.valor == null ? "—" : fmt(p.valor, Math.abs(p.valor) < 1 ? 6 : 4), p.unidad, p.cita || "—"])}
                  />
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </>
      )}
    </Card>
  );
}
