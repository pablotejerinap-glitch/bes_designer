"""
Data models for BES/ESP system design.
Based on: Kermit Brown, "The Technology of Artificial Lift Methods", Vol. 2b, Ch. 4.5.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class IPRMethod(Enum):
    """Inflow Performance Relationship method for reservoir modeling."""
    LINEAR = auto()       # Darcy / straight-line PI (above bubble point)
    VOGEL = auto()        # Vogel correlation (solution-gas drive)
    FETKOVICH = auto()    # Fetkovich empirical IPR


#: Correlaciones de pérdida de carga por fricción en el tubing que el usuario
#: puede elegir. Son strings y no un Enum a propósito: es el mismo vocabulario
#: que ya publica DesignResult.friction_method, así que lo elegido y lo
#: reportado se comparan sin traducir.
#:
#: Son TRES: una multifásica y dos monofásicas. Entre las dos monofásicas la
#: diferencia es la viscosidad — Hazen-Williams no la contempla y
#: Darcy-Weisbach sí—, y por debajo de 5 cp coinciden dentro del 2 %.
PRESSURE_LOSS_METHODS: frozenset[str] = frozenset(
    {"poettmann_carpenter", "hazen_williams", "darcy_weisbach"}
)


class DriveMechanism(Enum):
    """Primary reservoir energy source."""
    SOLUTION_GAS = auto()
    WATER_DRIVE = auto()
    GAS_CAP = auto()
    COMBINATION = auto()


@dataclass
class Reservoir:
    """Propiedades del reservorio: de dónde viene el fluido y con cuánta fuerza.

    La capacidad de aporte del pozo se carga normalmente como un **ensayo de
    producción** (``test_pwf`` + ``test_rate``), que es lo que realmente se mide
    a campo: se cierra el pozo, se lo deja estabilizar y se anota qué caudal da
    a qué presión de fondo. De ahí se deriva el índice de productividad con el
    método IPR elegido en ``ipr_method``.

    También se puede pasar ``productivity_index`` directo, para los casos en que
    sólo se publica el PI ya procesado — los ejemplos del libro de Brown, los
    informes de operadora.

    Attributes:
        static_pressure: Presión media actual del reservorio, Pr [psi]. Es la
            que hay con el pozo cerrado, sin producir.
        bubble_point: Presión de burbuja del fluido, Pb [psi]. Por debajo de
            ella el gas empieza a liberarse y la IPR se dobla.
        ipr_method: Qué correlación IPR aplicar (Lineal, Vogel o Fetkovich).
        reservoir_temp: Temperatura estática de fondo [°F].
        drive_mechanism: Mecanismo de empuje principal del reservorio.
        test_pwf: Presión de fondo fluyente estabilizada medida en el ensayo
            [psi]. Tiene que cumplir 0 <= test_pwf < static_pressure: un ensayo
            sin caída de presión no informa nada sobre la capacidad del pozo.
        test_rate: Caudal bruto de líquido estabilizado medido en ese mismo
            ensayo [STB/d]. Debe ser > 0.
        productivity_index: Índice de productividad J en las condiciones del
            ensayo [STB/d/psi]. Si se omite se deriva del ensayo; ver
            :func:`bes.core.ipr.productivity_index_from_test`.
        fetkovich_c: Coeficiente de entregabilidad C de Fetkovich
            [STB/d/psia^(2n)]. Si se omite y se conoce ``fetkovich_n``, se
            deriva del ensayo; si no, sale de un ensayo multi-caudal
            (flow-after-flow o isocronal).
        fetkovich_n: Exponente n de Fetkovich [-]. Rango físico [0.5, 1.0]:
            1.0 = laminar (sin turbulencia), 0.5 = totalmente turbulento.
            **Obligatorio** cuando ``ipr_method`` es FETKOVICH, porque un solo
            punto de ensayo no alcanza para ajustar C y n a la vez.
    """
    static_pressure: float
    bubble_point: float
    ipr_method: IPRMethod
    reservoir_temp: float
    drive_mechanism: DriveMechanism
    test_pwf: Optional[float] = None
    test_rate: Optional[float] = None
    productivity_index: Optional[float] = None
    fetkovich_c: Optional[float] = None
    fetkovich_n: Optional[float] = None

    def __post_init__(self) -> None:
        if self.static_pressure <= 0:
            raise ValueError(f"static_pressure must be > 0, got {self.static_pressure}")
        if self.bubble_point < 0:
            raise ValueError(f"bubble_point must be >= 0, got {self.bubble_point}")
        if self.bubble_point > self.static_pressure:
            import warnings
            warnings.warn(
                f"bubble_point ({self.bubble_point}) exceeds static_pressure "
                f"({self.static_pressure}). This is normal in depleted "
                f"reservoirs with solution gas drive (Vogel IPR applies).",
                UserWarning,
                stacklevel=2,
            )

        self._derive_deliverability_from_test()

        if self.ipr_method is IPRMethod.FETKOVICH:
            if self.fetkovich_c is None or self.fetkovich_n is None:
                raise ValueError(
                    "ipr_method FETKOVICH requires fetkovich_c and fetkovich_n "
                    "(from a multi-rate flow-after-flow or isochronal test), "
                    "or a production test (test_pwf/test_rate) plus fetkovich_n; "
                    f"got C={self.fetkovich_c}, n={self.fetkovich_n}"
                )
        if self.fetkovich_c is not None and self.fetkovich_c <= 0:
            raise ValueError(f"fetkovich_c must be > 0, got {self.fetkovich_c}")
        if self.fetkovich_n is not None and not (0.5 <= self.fetkovich_n <= 1.0):
            raise ValueError(
                f"fetkovich_n must be in [0.5, 1.0], got {self.fetkovich_n}"
            )
        if self.productivity_index is None:
            raise ValueError(
                "productivity_index could not be established: supply either a "
                "production test (test_pwf and test_rate) or productivity_index "
                "directly"
            )
        if self.productivity_index <= 0:
            raise ValueError(f"productivity_index must be > 0, got {self.productivity_index}")
        if self.reservoir_temp <= 0:
            raise ValueError(f"reservoir_temp must be > 0 °F, got {self.reservoir_temp}")

    def _derive_deliverability_from_test(self) -> None:
        """Completa el índice de productividad (y la C de Fetkovich) desde el ensayo.

        No hace nada cuando no se cargó ningún ensayo, ni cuando los valores que
        derivaría ya venían dados explícitamente: **el valor explícito siempre
        gana**, así que un caso que traiga a la vez un PI publicado y un punto de
        ensayo conserva el PI publicado.

        Raises:
            ValueError: Si se cargó sólo uno de ``test_pwf`` / ``test_rate``, o si
                el punto de ensayo es físicamente inválido.
        """
        has_pwf = self.test_pwf is not None
        has_rate = self.test_rate is not None
        if has_pwf != has_rate:
            raise ValueError(
                "a production test needs both test_pwf and test_rate; got "
                f"test_pwf={self.test_pwf}, test_rate={self.test_rate}"
            )
        if not has_pwf:
            return

        needs_pi = self.productivity_index is None
        needs_c = (
            self.ipr_method is IPRMethod.FETKOVICH
            and self.fetkovich_c is None
            and self.fetkovich_n is not None
        )
        if not (needs_pi or needs_c):
            return

        # Deferred import: bes.core.ipr imports this module at load time.
        from bes.core.ipr import productivity_index_from_test

        derived = productivity_index_from_test(
            pr=self.static_pressure,
            pwf_test=self.test_pwf,
            q_test=self.test_rate,
            method=self.ipr_method,
            fetkovich_n=self.fetkovich_n,
            # Vogel la necesita para separar el tramo recto (arriba de la
            # burbuja) del curvo. Sin ella se degrada a Vogel puro, que en un
            # reservorio subsaturado sobreestima J.
            bubble_point=self.bubble_point,
        )
        if needs_pi:
            self.productivity_index = derived["productivity_index"]
        if needs_c:
            self.fetkovich_c = derived["fetkovich_c"]


@dataclass
class Fluid:
    """El fluido que produce el pozo: qué es y cómo se comporta.

    Attributes:
        oil_api: Gravedad del petróleo en el tanque [°API]. Rango válido 5–70.
            Cuanto más alto, más liviano. Por debajo de 28 °API el crudo es
            pesado y hay que corregir la curva de la bomba por viscosidad.
        water_cut: Fracción de agua producida, en superficie [0–1]. 0.4 = 40 %
            de agua.
        gor: Relación gas-petróleo de producción, en superficie [scf/STB].
            Cuántos pies cúbicos de gas salen por cada barril de petróleo.
        gas_sg: Gravedad específica del gas (aire = 1.0).
        water_sg: Gravedad específica del agua de formación (agua pura = 1.0).
            Mayor a 1 porque trae sales disueltas.
        oil_viscosity_dead: Viscosidad del crudo sin gas, medida a
            ``viscosity_temp_ref`` [cp]. **Opcional**: ``None`` significa «no
            hay ensayo», y entonces la viscosidad se lee de la **Fig. 4L(2)**
            del libro con la °API y la temperatura de admisión
            (:func:`bes.core.viscosity.dead_oil_viscosity_chart`). Es el camino
            normal, no una excepción — de hecho un dato medido a otra
            temperatura se descarta y termina en la misma lámina.
            **``None``, no cero**: cero es un valor, y un crudo de viscosidad
            cero no existe.
        viscosity_temp_ref: Temperatura a la que se midió esa viscosidad [°F].
            Importa mucho: la viscosidad varía exponencialmente con la
            temperatura, así que un dato medido a otra temperatura no sirve.
            Obligatoria **si** hay viscosidad medida: un ensayo sin la
            temperatura a la que se hizo no se puede usar.
        bubble_point_pressure: Presión de burbuja del fluido, para el PVT [psi].
        h2s_content: Concentración de sulfuro de hidrógeno [ppm]. Afecta la
            elección de materiales — es corrosivo y tóxico.
        co2_content: Concentración de dióxido de carbono [ppm]. Afecta el
            diseño anticorrosivo.
        sand_production: True si el pozo produce arena, que desgasta la bomba y
            condiciona qué modelo se puede usar.
    """
    oil_api: float
    water_cut: float
    gor: float
    gas_sg: float
    water_sg: float
    oil_viscosity_dead: float | None
    viscosity_temp_ref: float | None
    bubble_point_pressure: float
    h2s_content: float
    co2_content: float
    sand_production: bool

    def __post_init__(self) -> None:
        if not (5.0 <= self.oil_api <= 70.0):
            raise ValueError(f"oil_api must be in [5, 70] °API, got {self.oil_api}")
        if not (0.0 <= self.water_cut <= 1.0):
            raise ValueError(f"water_cut must be in [0, 1], got {self.water_cut}")
        if self.gor < 0:
            raise ValueError(f"gor must be >= 0, got {self.gor}")
        if self.gas_sg <= 0:
            raise ValueError(f"gas_sg must be > 0, got {self.gas_sg}")
        if self.water_sg <= 0:
            raise ValueError(f"water_sg must be > 0, got {self.water_sg}")
        # La viscosidad medida es OPCIONAL: sin ensayo se lee la Fig. 4L(2).
        # Lo que no se acepta es un cero disfrazado de dato —un crudo de
        # viscosidad cero no existe— ni un ensayo sin la temperatura a la que
        # se hizo, que no se puede usar para nada.
        if self.oil_viscosity_dead is not None:
            if self.oil_viscosity_dead <= 0:
                raise ValueError(
                    f"oil_viscosity_dead must be > 0 or None (sin ensayo: se lee "
                    f"la Fig. 4L(2) del libro), got {self.oil_viscosity_dead}"
                )
            if self.viscosity_temp_ref is None:
                raise ValueError(
                    "viscosity_temp_ref es obligatoria cuando hay viscosidad "
                    "medida: sin la temperatura del ensayo el dato no se puede "
                    "usar, porque la viscosidad varía exponencialmente con ella."
                )
        if self.viscosity_temp_ref is not None and self.viscosity_temp_ref <= 0:
            raise ValueError(
                f"viscosity_temp_ref must be > 0 °F or None, got "
                f"{self.viscosity_temp_ref}"
            )
        if self.bubble_point_pressure < 0:
            raise ValueError(f"bubble_point_pressure must be >= 0, got {self.bubble_point_pressure}")
        if self.h2s_content < 0:
            raise ValueError(f"h2s_content must be >= 0, got {self.h2s_content}")
        if self.co2_content < 0:
            raise ValueError(f"co2_content must be >= 0, got {self.co2_content}")


@dataclass
class WellGeometry:
    """La geometría del pozo: el «tubo» por donde sube el fluido.

    Un pozo tiene dos cañerías concéntricas. El **casing** es la exterior, la que
    sostiene las paredes del pozo. El **tubing** es la interior, por donde sube la
    producción. El espacio entre las dos es el **anular**.

    La bomba se baja por adentro del casing, así que el ID del casing es la
    restricción física más dura de todo el diseño: si la bomba no entra, no entra.

    Attributes:
        total_depth: Profundidad medida hasta el fondo del pozo [ft MD].
        casing_od: Diámetro exterior del casing [in].
        casing_weight: Peso nominal del casing [lb/ft], que determina el espesor
            de pared.
        casing_id: Diámetro interior del casing (drift) [in]. **Limita el
            diámetro de la bomba.**
        tubing_od: Diámetro exterior del tubing de producción [in].
        tubing_id: Diámetro interior del tubing [in]. Gobierna las pérdidas por
            fricción: más angosto, más fricción.
        perforations_top: Profundidad medida al tope del intervalo
            punzado [ft MD].
        perforations_bottom: Profundidad medida a la base del intervalo
            punzado [ft MD].
        deviation_max: Inclinación máxima del pozo a lo largo de la sarta de
            producción [°]. Por encima de 30° puede hacer falta carcasa curva o
            eje flexible.
        wellhead_temp: Temperatura ambiente en superficie / boca de pozo [°F].
            Es el extremo superior del perfil geotérmico lineal; el inferior es
            ``Reservoir.reservoir_temp``. De ese perfil sale la temperatura a
            cualquier profundidad (``bes.core.tdh.temp_at_depth``), que alimenta
            el PVT del traverse de presión, la temperatura de admisión de la
            bomba y la corrección por viscosidad.
        pump_setting_depth: Profundidad de succión — dónde se asienta la
            admisión de la bomba [ft MD]. **Opcional**: cuando se deja en
            ``None`` se calcula como ``perforations_top − safety_margin_depth``
            (Brown §4.532), que es el comportamiento por defecto. Cargarla
            explícitamente sirve para reproducir los ejemplos del libro, donde
            la profundidad viene dada (5850 ft en el #2A, 7000 ft en el #3B),
            y para respetar una instalación ya existente.

            Manda sobre buena parte del diseño: fija el PIP y con él la
            sumergencia del TDH, el largo de cable y su caída de tensión, y la
            temperatura a la que trabaja el motor.
    """
    total_depth: float
    casing_od: float
    casing_weight: float
    casing_id: float
    tubing_od: float
    tubing_id: float
    perforations_top: float
    perforations_bottom: float
    deviation_max: float
    wellhead_temp: float
    pump_setting_depth: Optional[float] = None

    def __post_init__(self) -> None:
        if self.total_depth <= 0:
            raise ValueError(f"total_depth must be > 0, got {self.total_depth}")
        if self.casing_od <= 0:
            raise ValueError(f"casing_od must be > 0, got {self.casing_od}")
        if self.casing_weight <= 0:
            raise ValueError(f"casing_weight must be > 0, got {self.casing_weight}")
        if self.casing_id <= 0:
            raise ValueError(f"casing_id must be > 0, got {self.casing_id}")
        if self.casing_id >= self.casing_od:
            raise ValueError(
                f"casing_id ({self.casing_id}) must be < casing_od ({self.casing_od})"
            )
        if self.tubing_od <= 0:
            raise ValueError(f"tubing_od must be > 0, got {self.tubing_od}")
        if self.tubing_id <= 0:
            raise ValueError(f"tubing_id must be > 0, got {self.tubing_id}")
        if self.tubing_id >= self.tubing_od:
            raise ValueError(
                f"tubing_id ({self.tubing_id}) must be < tubing_od ({self.tubing_od})"
            )
        if self.tubing_od >= self.casing_id:
            raise ValueError(
                f"tubing_od ({self.tubing_od}) must be < casing_id ({self.casing_id})"
            )
        if self.perforations_top <= 0:
            raise ValueError(f"perforations_top must be > 0, got {self.perforations_top}")
        if self.perforations_bottom <= self.perforations_top:
            raise ValueError(
                f"perforations_bottom ({self.perforations_bottom}) must be "
                f"> perforations_top ({self.perforations_top})"
            )
        if self.perforations_bottom > self.total_depth:
            raise ValueError(
                f"perforations_bottom ({self.perforations_bottom}) cannot exceed "
                f"total_depth ({self.total_depth})"
            )
        if not (0.0 <= self.deviation_max <= 90.0):
            raise ValueError(f"deviation_max must be in [0, 90]°, got {self.deviation_max}")
        if self.wellhead_temp <= 0:
            raise ValueError(f"wellhead_temp must be > 0 °F, got {self.wellhead_temp}")
        if self.pump_setting_depth is not None:
            # La bomba va DENTRO del pozo y POR ENCIMA de las perforaciones: si
            # se asentara más abajo, el fluido tendría que bajar para entrar.
            if self.pump_setting_depth <= 0:
                raise ValueError(
                    f"pump_setting_depth must be > 0, got {self.pump_setting_depth}"
                )
            if self.pump_setting_depth >= self.perforations_top:
                raise ValueError(
                    f"pump_setting_depth ({self.pump_setting_depth}) must be "
                    f"above perforations_top ({self.perforations_top}): la bomba "
                    f"se asienta por encima del intervalo punzado"
                )


@dataclass
class SurfaceConditions:
    """Lo que hay en la superficie: la instalación y la energía disponible.

    Attributes:
        wellhead_pressure_required: Presión mínima necesaria en boca de
            pozo [psi]. La bomba tiene que entregar el fluido con esta presión
            para que llegue al separador.
        flowline_length: Largo de la línea de conducción, de la boca de pozo al
            separador [ft].
        flowline_id: Diámetro interior de la línea de conducción [in].
        flowline_elevation_change: Desnivel neto a lo largo de la línea
            (+ = cuesta arriba) [ft].
        separator_pressure: Presión de operación del separador de
            producción [psi].
        power_supply_voltage: Tensión disponible en superficie [V].
        frequency: Frecuencia de la red eléctrica [Hz]. Típicamente 60 (América)
            o 50 (resto del mundo). **Importa mucho**: la curva de la bomba se
            reescala a esta frecuencia antes de elegir nada.
    """
    wellhead_pressure_required: float
    flowline_length: float
    flowline_id: float
    flowline_elevation_change: float
    separator_pressure: float
    power_supply_voltage: float
    frequency: float

    def __post_init__(self) -> None:
        if self.wellhead_pressure_required < 0:
            raise ValueError(
                f"wellhead_pressure_required must be >= 0, got {self.wellhead_pressure_required}"
            )
        if self.flowline_length < 0:
            raise ValueError(f"flowline_length must be >= 0, got {self.flowline_length}")
        if self.flowline_id <= 0:
            raise ValueError(f"flowline_id must be > 0, got {self.flowline_id}")
        if self.separator_pressure < 0:
            raise ValueError(f"separator_pressure must be >= 0, got {self.separator_pressure}")
        if self.power_supply_voltage <= 0:
            raise ValueError(f"power_supply_voltage must be > 0, got {self.power_supply_voltage}")
        if self.frequency not in (50.0, 60.0):
            raise ValueError(f"frequency must be 50 or 60 Hz, got {self.frequency}")


@dataclass
class DesignObjectives:
    """Lo que el usuario pide y las restricciones que impone al diseño.

    Attributes:
        target_flow_rate: Caudal bruto de líquido que se quiere producir
            [STB/d]. Es el dato que dispara todo el cálculo.
        safety_margin_depth: Profundidad extra por encima de las punzados donde
            se asienta la bomba, como margen operativo [ft]. Se deja para que la
            bomba no quede tapada si baja el nivel de fluido.
        allow_gas_venting: Si es True, se supone que hay venteo por el anular o
            separador de gas disponible.
        max_gip: **Fracción** máxima de gas libre admisible a la entrada de la
            bomba, ya descontados el venteo por el anular y el separador [0–1].
            Por encima de este valor el diseño BES no converge y corresponde
            evaluar otro método de levantamiento artificial: lo verifica
            ``bes.core.gas_handling.evaluate_gas_feasibility()`` y el diseño
            **falla**, no advierte.

            Es una FRACCIÓN ``V_gas/(V_gas+V_líquido)``, no una relación
            ``V_gas/V_líquido``. El default coincide con
            ``gas_handling.GAS_FRACTION_PUMP_LIMIT``; no se importa de ahí
            porque ``gas_handling`` importa este módulo y sería circular.

            **Historia:** el campo existía desde el principio, se imprimía en
            el PDF y el Excel, y **ningún cálculo lo leía**. Los casos guardados
            de esa época traen valores como 0.7, que nunca significaron nada y
            ahora sí: con 0.7 cargado, un pozo con 70 % de gas en la bomba
            pasaría la verificación. Revisar los casos viejos.
        design_life_years: Vida útil esperada del equipo, para dimensionar y
            fijar objetivos de MTBF [años].
        use_vsd: Si es True, el diseño incluye variador de frecuencia (VSD/VFD).
        gas_fraction_pc_threshold: Fracción volumétrica de gas libre en la
            admisión por encima de la cual la pérdida de carga en el tubing se
            calcula con Poettmann-Carpenter en vez de Hazen-Williams [0–1].

            **No es un parámetro de diseño y NO se pide por pantalla ni por la
            API.** El umbral lo fija la física, no el usuario: con más del 1 %
            de gas libre, usar un gradiente de líquido constante introduce un
            error de diseño grande (Brown Vol. 2b §4.53102; Takács, *ESP
            Manual*). El programa decide solo qué correlación corresponde.

            Queda como parámetro únicamente para poder **reproducir los
            ejemplos impresos** de Brown, que se resuelven a mano como
            monofásicos y necesitan fijarlo en 1.0. Sólo los tests lo tocan.

            El valor por defecto tiene que coincidir con
            ``bes.core.gas_handling.GAS_FRACTION_NEGLIGIBLE``; no se importa de
            ahí porque ``gas_handling`` importa este módulo y sería circular.
            ``tests/test_gas_handling.py`` verifica que no se desincronicen.
        pressure_loss_method: Con qué correlación se calcula la **pérdida de
            carga por fricción en el tubing**. ``"poettmann_carpenter"`` o
            ``"hazen_williams"``; ``None`` —el default— deja que decida la
            física, que es el comportamiento histórico.

            Es lo ÚNICO que el usuario elige de esta cuenta. El umbral de gas
            (``gas_fraction_pc_threshold``) sigue sin exponerse: una cosa es
            elegir el método y otra mover el corte con que se lo elige solo.

            Con ``None`` manda la fracción de gas libre en la admisión, igual
            que siempre. Con un método elegido a mano, ese método se usa, y si
            la física no coincide con la elección el diseño **avisa** en vez de
            corregir en silencio: el usuario manda, pero enterado.

            Elegir ``"poettmann_carpenter"`` además activa la verificación del
            envelope declarado del método —tubing de 2, 2½ o 3 pulg, menos de
            5 cp, RGL menor a 1500 scf/bbl y más de 400 bbl/d—, que vive en
            :func:`bes.core.multiphase.poettmann_carpenter_applicability`. El
            límite del tubing es duro; los otros tres avisan.
        design_frequency_hz: Frecuencia a la que va a girar realmente la bomba
            [Hz]. ``None`` = la frecuencia de red de
            ``SurfaceConditions.frequency``. Sólo tiene sentido con ``use_vsd``:
            un tablero fijo hace girar la bomba a la frecuencia de línea, un
            variador no. La curva de la bomba se reescala a esta frecuencia con
            las leyes de afinidad **antes** de elegir nada — ver
            :func:`bes.core.affinity.pump_at_frequency`.
    """
    target_flow_rate: float
    safety_margin_depth: float
    allow_gas_venting: bool
    design_life_years: float
    use_vsd: bool
    # max_gip quedó DESPUÉS de los obligatorios para poder llevar default. Todas
    # las construcciones del proyecto son por keyword, así que el reordenamiento
    # no rompe llamadas posicionales.
    max_gip: float = 0.10
    gas_fraction_pc_threshold: float = 0.01
    pressure_loss_method: Optional[str] = None
    design_frequency_hz: Optional[float] = None

    def __post_init__(self) -> None:
        if self.pressure_loss_method is not None:
            if self.pressure_loss_method not in PRESSURE_LOSS_METHODS:
                raise ValueError(
                    "pressure_loss_method must be one of "
                    f"{sorted(PRESSURE_LOSS_METHODS)} or None, got "
                    f"{self.pressure_loss_method!r}"
                )
        if not (0.0 <= self.gas_fraction_pc_threshold <= 1.0):
            raise ValueError(
                "gas_fraction_pc_threshold must be in [0, 1], got "
                f"{self.gas_fraction_pc_threshold}"
            )
        if self.design_frequency_hz is not None:
            if not (20.0 <= self.design_frequency_hz <= 90.0):
                raise ValueError(
                    "design_frequency_hz must be in [20, 90] Hz (VSD operating "
                    f"range), got {self.design_frequency_hz}"
                )
            if not self.use_vsd:
                raise ValueError(
                    "design_frequency_hz requires use_vsd=True: without a "
                    "variable-speed drive the pump runs at line frequency"
                )
        if self.target_flow_rate <= 0:
            raise ValueError(f"target_flow_rate must be > 0, got {self.target_flow_rate}")
        if self.safety_margin_depth < 0:
            raise ValueError(f"safety_margin_depth must be >= 0, got {self.safety_margin_depth}")
        if not (0.0 <= self.max_gip <= 1.0):
            raise ValueError(f"max_gip must be in [0, 1], got {self.max_gip}")
        if self.design_life_years <= 0:
            raise ValueError(f"design_life_years must be > 0, got {self.design_life_years}")


@dataclass
class PumpPerformancePoint:
    """Un punto de la curva de comportamiento de una bomba.

    La curva de catálogo es una lista de estos puntos: para cada caudal, qué
    altura entrega una etapa, cuánta potencia consume y con qué rendimiento.

    Attributes:
        flow_rate: Caudal en este punto [b/d].
        head_per_stage: Altura hidráulica que desarrolla una etapa a ese
            caudal [ft/etapa].
        hp_per_stage: Potencia al eje que consume una etapa [hp/etapa].
        efficiency: Rendimiento hidráulico de la bomba en este punto [0–1].
    """
    flow_rate: float
    head_per_stage: float
    hp_per_stage: float
    efficiency: float

    def __post_init__(self) -> None:
        if self.flow_rate < 0:
            raise ValueError(f"flow_rate must be >= 0, got {self.flow_rate}")
        if self.head_per_stage < 0:
            raise ValueError(f"head_per_stage must be >= 0, got {self.head_per_stage}")
        if self.hp_per_stage < 0:
            raise ValueError(f"hp_per_stage must be >= 0, got {self.hp_per_stage}")
        if not (0.0 <= self.efficiency <= 1.0):
            raise ValueError(f"efficiency must be in [0, 1], got {self.efficiency}")


@dataclass
class PumpHousing:
    """Una carcasa: el recipiente donde se alojan las etapas de la bomba.

    Los fabricantes venden carcasas en un conjunto discreto de longitudes, cada
    una con capacidad para una cantidad fija de etapas. Un diseño que necesita
    más etapas de las que entran en la carcasa más grande se arma como un
    **tándem**: varias carcasas en serie.

    Sólo ``stages`` es obligatorio — es el único atributo que publican hoy todos
    los catálogos del proyecto. El resto son **metadatos opcionales** que quedan
    vacíos hasta que se cargue el dato del fabricante. El algoritmo de selección
    no necesita ninguno, así que un catálogo se puede enriquecer más adelante sin
    tocar código.

    Attributes:
        stages: Capacidad de esta carcasa [etapas]. Debe ser > 0.
        code: Código o número de parte del fabricante. Vacío si no se conoce.
        material: Material de la carcasa (por ej. "Carbon steel", "Ni-Resist").
            Vacío cuando el catálogo no lo publica.
        od_in: Diámetro exterior de la carcasa [in]. 0 = se desconoce, y se usa
            el de la bomba.
        pressure_limit_psi: Presión de trabajo que aguanta **esta** carcasa
            [psi]. 0 = se desconoce, y entonces rige el límite a nivel bomba.
            Un valor distinto de cero permite armar un tándem que mezcle
            carcasas estándar y de alta presión, poniendo la mejor calificada
            donde la presión es mayor.
        length_ft: Largo de la carcasa [ft]. 0 = se desconoce.
        weight_lbs: Peso de la carcasa [lbs]. 0 = se desconoce.
    """
    stages: int
    code: str = ""
    material: str = ""
    od_in: float = 0.0
    pressure_limit_psi: float = 0.0
    length_ft: float = 0.0
    weight_lbs: float = 0.0

    def __post_init__(self) -> None:
        if self.stages <= 0:
            raise ValueError(f"stages must be > 0, got {self.stages}")
        if self.od_in < 0:
            raise ValueError(f"od_in must be >= 0, got {self.od_in}")
        if self.pressure_limit_psi < 0:
            raise ValueError(
                f"pressure_limit_psi must be >= 0, got {self.pressure_limit_psi}"
            )


@dataclass
class PumpCurve:
    """Una bomba del catálogo, con su curva de comportamiento completa.

    La **curva** es lo que publica el fabricante: para cada caudal, cuánta altura
    entrega una etapa, cuánta potencia consume y con qué rendimiento. Está
    levantada con agua limpia y para **una sola etapa**; el diseño la escala a la
    frecuencia real y la multiplica por la cantidad de etapas.

    Attributes:
        manufacturer: Fabricante del equipo (por ej. "REDA", "Centrilift").
        series: Serie o línea de producto (por ej. "DN1750", "GC6100").
        model: Designación del modelo.
        od: Diámetro exterior de la bomba [in]. Tiene que entrar en el casing.
        min_flow: Caudal mínimo recomendado de operación [b/d]. Por debajo, la
            bomba trabaja en downthrust y se desgasta.
        max_flow: Caudal máximo recomendado de operación [b/d]. Por encima,
            trabaja en upthrust.
        bep_flow: Caudal del punto de máximo rendimiento (BEP) [b/d]. Es donde
            conviene hacerla trabajar.
        points: Puntos de la curva que cubren el rango de operación.
        max_stages: Máxima cantidad de etapas disponible en esta carcasa.
        housing_options: Tamaños de carcasa disponibles, en cantidad de etapas.
        housings: Catálogo completo de carcasas de esta bomba. Se sintetiza
            desde ``housing_options`` cuando el catálogo trae sólo las
            cantidades de etapas, así quien llama siempre puede trabajar con
            objetos :class:`PumpHousing`.
    """
    manufacturer: str
    series: str
    model: str
    od: float
    min_flow: float
    max_flow: float
    bep_flow: float
    points: list[PumpPerformancePoint]
    max_stages: int
    housing_options: list[int]
    # Presión máxima de trabajo de la carcasa [psi] (opcional; 0 = sin dato).
    housing_pressure_limit_psi: float = 0.0
    housings: list[PumpHousing] = field(default_factory=list)
    # Frecuencia a la que el fabricante publicó la curva [Hz]. Es el punto de
    # partida de las leyes de afinidad (bes.core.affinity). 60 Hz por defecto:
    # es la frecuencia declarada en el _source de los catálogos digitalizados y
    # la de los ejemplos del libro de Brown.
    catalog_frequency_hz: float = 60.0

    def __post_init__(self) -> None:
        if self.od <= 0:
            raise ValueError(f"od must be > 0, got {self.od}")
        if self.min_flow < 0:
            raise ValueError(f"min_flow must be >= 0, got {self.min_flow}")
        if self.max_flow <= self.min_flow:
            raise ValueError(
                f"max_flow ({self.max_flow}) must be > min_flow ({self.min_flow})"
            )
        if not (self.min_flow <= self.bep_flow <= self.max_flow):
            raise ValueError(
                f"bep_flow ({self.bep_flow}) must be in "
                f"[min_flow={self.min_flow}, max_flow={self.max_flow}]"
            )
        if not self.points:
            raise ValueError("points list cannot be empty")
        if self.max_stages <= 0:
            raise ValueError(f"max_stages must be > 0, got {self.max_stages}")
        if not self.housing_options:
            raise ValueError("housing_options list cannot be empty")
        if any(s <= 0 for s in self.housing_options):
            raise ValueError("all housing_options values must be > 0")
        if not self.manufacturer.strip():
            raise ValueError("manufacturer cannot be empty")
        if not self.model.strip():
            raise ValueError("model cannot be empty")
        # Un catálogo que solo publica las longitudes disponibles (el caso de
        # todos los catálogos actuales) queda igualmente expresado como objetos
        # PumpHousing, sin metadatos. Así el selector tiene una sola forma de
        # leer las carcasas y enriquecer el catálogo no toca código.
        if not self.housings:
            self.housings = [
                PumpHousing(stages=int(s)) for s in sorted(set(self.housing_options))
            ]


@dataclass
class DesignResult:
    """El resultado completo de un diseño BES: todo el aparejo, de punta a punta.

    Es el objeto que viaja a la pantalla, al PDF y al Excel. Reúne lo hidráulico
    (bomba, etapas, altura) con lo eléctrico (motor, cable, transformador) y con
    las advertencias que el ingeniero tiene que revisar.

    Attributes:
        pump_manufacturer: Fabricante de la bomba elegida.
        pump_series: Serie de la bomba elegida.
        pump_model: Modelo de la bomba elegida.
        pump_od: Diámetro exterior de la bomba [in].
        num_stages: Cantidad de etapas necesarias.
        pump_setting_depth: Profundidad de asentamiento recomendada [ft MD].
        intake_pressure: Presión en la admisión de la bomba, PIP [psi].
        total_head_required: Altura dinámica total que debe desarrollar la
            bomba, TDH [ft].
        head_per_stage: Altura por etapa en el punto de operación [ft/etapa].
        hp_per_stage: Potencia por etapa en el punto de operación [hp/etapa].
        pump_efficiency: Rendimiento hidráulico de la bomba en el punto de
            operación [0–1].
        total_pump_hp: Potencia total al eje de la bomba [hp].
        motor_manufacturer: Fabricante del motor elegido.
        motor_model: Modelo del motor.
        motor_hp: Potencia de placa del motor [hp].
        motor_voltage: Tensión de placa del motor [V].
        motor_amperage: Corriente de placa a carga nominal [A].
        motor_od: Diámetro exterior del motor [in].
        motor_length: Largo del motor, simple o apilado [ft].
        cable_type: Tipo de cubierta o clase de aislación del cable (por ej.
            "EPDM", "Polypro").
        cable_awg: Calibre del conductor [AWG].
        cable_voltage_drop: Caída de tensión estimada a lo largo del cable [V].
        surface_voltage_required: Tensión necesaria en superficie para que al
            motor le llegue la suya [V].
        transformer_kva: Potencia recomendada del transformador [kVA].
        system_efficiency: Rendimiento global del sistema
            (bomba × motor × cable) [0–1].
        flow_rate_achieved: Caudal bruto de líquido calculado en el punto de
            operación [STB/d].
        operating_frequency: Frecuencia de operación de la bomba [Hz],
            relevante en diseños con variador.
        gip_fraction: Fracción de gas libre estimada en la admisión [0–1].
        warnings: Advertencias del diseño que el ingeniero tiene que revisar.
        alternatives: Combinaciones alternativas de equipo que se consideraron.
    """
    pump_manufacturer: str
    pump_series: str
    pump_model: str
    pump_od: float
    num_stages: int
    pump_setting_depth: float
    intake_pressure: float
    total_head_required: float
    head_per_stage: float
    hp_per_stage: float
    pump_efficiency: float
    total_pump_hp: float
    motor_manufacturer: str
    motor_model: str
    motor_hp: float
    motor_voltage: float
    motor_amperage: float
    motor_od: float
    motor_length: float
    cable_type: str
    cable_awg: int
    cable_voltage_drop: float
    surface_voltage_required: float
    transformer_kva: float
    system_efficiency: float
    flow_rate_achieved: float
    operating_frequency: float
    gip_fraction: float
    warnings: list[str] = field(default_factory=list)

    # Traza de fórmulas: cada cuenta del diseño con su expresión simbólica, los
    # números reemplazados, el resultado y la cita bibliográfica. La arma el
    # propio código que calcula (ver bes/core/formulas.py), así no puede decir
    # una cosa y el programa hacer otra.
    formulas: list[dict] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    # Correlación con la que se calculó la pérdida de carga en el tubing:
    # "hazen_williams" (monofásica) o "poettmann_carpenter" (multifásica), según
    # la fracción de gas libre en la admisión frente al umbral de objetivos.
    friction_method: str = "hazen_williams"
    gas_fraction_threshold: float = 0.10
    # Housing / carcasas (poblado por bes.core.housing.optimize_housings)
    housing_size_stages: int = 0     # capacidad total instalada [etapas]
    dummy_stages: int = 0            # etapas ciegas para completar la carcasa
    n_housings: int = 1              # nº de carcasas/unidades (>1 = tándem)
    max_housing_pressure_psi: float = 0.0   # MaxP shut-in sobre la carcasa superior
    housing_pressure_limit_psi: float = 0.0 # límite de trabajo de la carcasa
    housing_pressure_ok: bool = True         # MaxP <= límite en TODAS las carcasas
    # Ficha por carcasa, de la admisión a la descarga: posición, etapas, código,
    # material, OD, etapas activas por debajo, presión calculada, límite y OK.
    housing_detail: list[dict] = field(default_factory=list)
    housing_rationale: str = ""      # justificación técnica de la combinación
    housing_pressure_verified: bool = False  # False = el catálogo no publica el límite
    # Verificación mecánica de la serie (bes.core.mechanical). Vacías cuando el
    # catálogo no tiene ficha de la serie: sin verificar, nunca aprobadas.
    shaft_check: dict = field(default_factory=dict)      # HP eje vs límite std/HR
    bearing_check: dict = field(default_factory=dict)    # etapas vs cojinete y BHT
    bearing_load_lbs: float = 0.0    # Carga TL = Ho × Pem × A_eje
    staging_ceiling: dict = field(default_factory=dict)  # tope por housing/eje/cojinete
    # Enfriamiento del motor (velocidad de fluido en el anular)
    fluid_velocity_ft_s: float = 0.0
    cooling_ok: bool = True
    # HP máximo de eje (fluido más pesado); el motor se dimensiona sobre este.
    # ``total_pump_hp`` es el HP operativo (SG de la mezcla).
    motor_hp_max: float = 0.0
    # Controlador de superficie (tablero fijo o VSD)
    controller_manufacturer: str = ""
    controller_model: str = ""
    controller_type: str = ""
    # Seal / protector (optional; populated by the electrical design)
    seal_manufacturer: str = ""
    seal_model: str = ""
    seal_type: str = ""
    seal_thrust_capacity_lbs: float = 0.0
    axial_thrust_lbs: float = 0.0
    # Gas handler / separator (optional; recommended only when free gas warrants)
    gas_handler_manufacturer: str = ""
    gas_handler_model: str = ""
    gas_handler_type: str = ""
    gas_handler_efficiency: float = 0.0
    # Potencia que consumen los manejadores de gas y que el motor tiene que
    # mover ADEMÁS de la bomba. 0.0 cuando el aparejo no lleva ninguno. Se
    # publica aparte para que se pueda auditar, en vez de quedar escondida
    # dentro del HP con que se eligió el motor.
    gas_handler_hp: float = 0.0
    # Zona operativa del método de incrementos (pozos con gas). Los tres valen
    # 0.0 en el camino convencional, donde el caudal es uno solo y la pregunta
    # no existe. Ver bes.plotting.plots._draw_gas_zone.
    gas_q_representative_bpd: float = 0.0
    gas_q_intake_bpd: float = 0.0
    gas_q_discharge_bpd: float = 0.0
    # Cuántos separadores lleva el aparejo. 2 = TÁNDEM, la mayor capacidad de
    # manejo de gas de la tecnología BES (Takács, Fig. 4.25), armado con dos
    # tipos distintos de separador.
    gas_handler_count: int = 0
    # Escalón de la escalera de manejo de gas que resolvió el pozo:
    # "ninguno" / "simple" / "tandem" / "no_viable".
    gas_strategy: str = ""
    # Fracción de gas libre que efectivamente le llega a la bomba, DESPUÉS de
    # ventear y separar. Es la que se compara contra ``max_gip``; distinta de
    # ``gip_fraction``, que es la de la admisión antes de separar.
    gas_fraction_at_pump: float = 0.0
    # ``True`` cuando ni el tándem alcanza: no hay equipo BES que resuelva este
    # pozo y corresponde evaluar otro método de levantamiento artificial.
    switch_lift_method: bool = False
    # El texto del veredicto de gas, para mostrar y para el reporte.
    gas_verdict: str = ""
    # Downhole sensor (optional; recommended for monitoring)
    sensor_manufacturer: str = ""
    sensor_model: str = ""

    def __post_init__(self) -> None:
        if self.num_stages <= 0:
            raise ValueError(f"num_stages must be > 0, got {self.num_stages}")
        if self.pump_setting_depth <= 0:
            raise ValueError(f"pump_setting_depth must be > 0, got {self.pump_setting_depth}")
        if self.intake_pressure <= 0:
            raise ValueError(f"intake_pressure must be > 0, got {self.intake_pressure}")
        if self.total_head_required <= 0:
            raise ValueError(f"total_head_required must be > 0, got {self.total_head_required}")
        if not (0.0 <= self.pump_efficiency <= 1.0):
            raise ValueError(f"pump_efficiency must be in [0, 1], got {self.pump_efficiency}")
        if not (0.0 <= self.system_efficiency <= 1.0):
            raise ValueError(f"system_efficiency must be in [0, 1], got {self.system_efficiency}")
        if self.flow_rate_achieved <= 0:
            raise ValueError(f"flow_rate_achieved must be > 0, got {self.flow_rate_achieved}")
        if not (0.0 <= self.gip_fraction <= 1.0):
            raise ValueError(f"gip_fraction must be in [0, 1], got {self.gip_fraction}")
        if self.motor_hp <= 0:
            raise ValueError(f"motor_hp must be > 0, got {self.motor_hp}")
        if self.motor_voltage <= 0:
            raise ValueError(f"motor_voltage must be > 0, got {self.motor_voltage}")
        if self.transformer_kva <= 0:
            raise ValueError(f"transformer_kva must be > 0, got {self.transformer_kva}")
        if self.cable_awg <= 0:
            raise ValueError(f"cable_awg must be > 0, got {self.cable_awg}")
        if not self.pump_manufacturer.strip():
            raise ValueError("pump_manufacturer cannot be empty")
        if not self.motor_manufacturer.strip():
            raise ValueError("motor_manufacturer cannot be empty")
