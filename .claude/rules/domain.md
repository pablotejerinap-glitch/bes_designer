# Reglas de dominio — BES Designer

## Regla de oro (validación contra el libro)

Toda correlación o cálculo nuevo del dominio se **valida contra un ejemplo
numerado del libro de Kermit Brown** (*The Technology of Artificial Lift
Methods*, Vol. 2b, Cap. 4.5) y se agrega un test. La disciplina de los **545
tests verdes** es el activo más valioso del proyecto — no romperla.

Ejemplos de referencia usados como tests de regresión:

| Ejemplo | Bomba | Caudal (bpd) | TDH (ft) | Etapas | HP |
|---|---|---|---|---|---|
| #1A | Centrilift I-300 | 10 000 | 1 670 | 28 | 180 |
| #2A | Reda D-40 | 1 227 | 5 830 | 254 | ≈79 |
| #2B | Centrilift I-42B | ~2 080 | 4 258 | 112 | ≈65 |

Datos en `data/example_wells.json`; tests en `tests/`.

## Convención de unidades

| Magnitud | Unidad |
|---|---|
| Presión | psia (diferenciales en psi) |
| Temperatura | °F |
| Caudal | STB/d (superficie) o bpd |
| Profundidad / longitud | ft TVD o ft MD |
| Diámetros | pulgadas |
| Potencia | hp |
| Voltaje / corriente | V / A |

`hp/stage` del catálogo está calibrado para agua (SG = 1.0); multiplicar por
`sg_fluid` para el HP real.

## Glosario ESP/BES (para quien no es de petróleo)

- **BES / ESP**: Bombeo Electrosumergible / Electric Submersible Pump.
- **IPR** (Inflow Performance Relationship): capacidad de aporte del reservorio
  (caudal vs. presión de fondo). Métodos: Vogel, Linear, Fetkovich, Combined.
- **PVT**: propiedades del fluido (Bo, Rs, Pb, viscosidad, z-factor) según presión/temp.
- **Pwf**: presión de fondo fluyente en las perforaciones.
- **PIP** (Pump Intake Pressure): presión en la admisión de la bomba.
- **TDH** (Total Dynamic Head): altura total que debe desarrollar la bomba =
  Vertical Lift + Fricción de tubería + Head de presión en superficie.
- **BEP** (Best Efficiency Point): caudal de máxima eficiencia de la bomba.
- **GIP / GIP fraction**: fracción de gas libre en la admisión de la bomba.
- **VSD/VFD**: variador de frecuencia.
- **Stage (etapa)**: cada impulsor+difusor de la bomba; se apilan para dar TDH.

## Fórmula de TDH (Brown §4.5324)

```
TDH = Vertical Lift + Fricción de tubería + Head de presión en superficie
Vertical Lift  = pump_depth − (PIP × 2.31 / SG_liquid)
Fricción       = Hazen-Williams
Head Pwh       = Pwh × 2.31 / SG_liquid
```
