import os
import time
import pvlib
import numpy as np
import pandas as pd
from typing import Literal
from weather import OpenMeteoClient
from datetime import datetime, timedelta
from utils import Constants, Logger, Symbols


class SolarPV:

    INDEX_NAME: str = "tick"
    VARIABLES: list[str] = [
        "poa_global",
        "cell_temperature",
        "power_dc",
        "power_ac",
    ]

    FILENAME: str = f"{os.path.dirname(os.path.abspath(__file__))}/solarpv"

    def __init__(
        self,
        name: str,
        latitude: float,
        longitude: float,
        n_panels: int,
        pdc0: float,
        gamma_pdc: float,
        ratio_dc_ac: float,
        eta_inv: float,
        surface_tilt: float,
        surface_azimuth: float,
        surface_type: Literal[
            "urban",
            "grass",
            "fresh grass",
            "snow",
            "fresh snow",
            "asphalt",
            "concrete",
            "aluminum",
            "copper",
            "fresh steel",
            "dirty steel",
            "sea",
        ] = "grass",
        toLog: bool = True,
    ):
        """

        Args:
            name (str): name.
            latitude (float): latitude [degree].
            longitude (float): longitude [degree].
            n_panels (float): number of PV panels.
            pdc0 (float): DC power at refence conditions (1000 W/m^2 and 25 C) [W].
            gamma_pdc (float): temperature coefficient of power [1/C].
            ratio_dc_ac (float): DC-to-AC ratio.
            eta_inv (float): inverter efficiency (nominal) [0 - 1].
            surface_tilt (float): surface tilt from horizontal [degree].
            surface_azimuth (float): surface azimuth from north [degree].
            surface_type (str): surface type. Defaults to "grass".
            toLog (bool):
        """
        self.latitude = latitude
        self.longitude = longitude
        self.n_panels = n_panels
        self.pdc0 = pdc0
        self.gamma_pdc = gamma_pdc
        self.ratio_dc_ac = ratio_dc_ac
        self.eta_inv = eta_inv
        self.surface_tilt = surface_tilt
        self.surface_azimuth = surface_azimuth
        self.surface_type = surface_type
        self.albedo = pvlib.albedo.SURFACE_ALBEDOS[surface_type]

        # pvlib
        self.location = pvlib.location.Location(
            latitude=latitude,
            longitude=longitude,
            tz=Constants.TIME_ZONE_NAME,
            name=name,
        )

        # weather
        self.omc = OpenMeteoClient(
            location=name,
            latitude=latitude,
            longitude=longitude,
            toLog=False,
        )
        self.omc.connect()

        self.logger = Logger(name=f"SolarPV: {name}", toLog=toLog)
        return self.logger.log(
            f"initialised at the location '{latitude:.3f} N {longitude:.3f} E' with '{n_panels}' panels, nominal DC power '{pdc0}' W, temperature coeff. of power '{gamma_pdc*100:.2f} %/{Symbols.DEGREE}C', DC:AC ratio '{ratio_dc_ac:.2f}', inverter efficiency '{eta_inv:0.2f}', surface tilt '{surface_tilt}{Symbols.DEGREE}', azimuth '{surface_azimuth}{Symbols.DEGREE}', type '{surface_type}' and ground surface albedo '{self.albedo:.2f}'."
        )

    def predict(
        self,
        tStart: datetime,
        tEnd: datetime,
        tInt: int,
        isForecast: bool,
        toRecord: bool = True,
        toPrint: bool = False,
    ) -> pd.DataFrame:

        if toRecord:
            tStart = tStart.replace(minute=0, second=0, microsecond=0)
            tEnd = tEnd.replace(minute=0, second=0, microsecond=0)
            tInt = 60
            ticks = pd.date_range(
                start=tStart,
                end=tEnd,
                freq=f"{tInt}min",
                tz=Constants.TIME_ZONE_INFO,
            )

            if isForecast:
                dataType = "forecast"
            elif not isForecast:
                dataType = "historical"

            filePath = f"{self.FILENAME}_{dataType}.csv"

            if os.path.exists(filePath):
                df = pd.read_csv(filePath, index_col=self.INDEX_NAME, parse_dates=True)
                if not isinstance(df.index, pd.DatetimeIndex):
                    df.index = pd.to_datetime(df.index, utc=True).tz_convert(
                        Constants.TIME_ZONE_NAME
                    )
                if df.empty:
                    toCreateFile = True
                elif ticks.isin(df.index).all():
                    toCreateFile = False
                    self.logger.log(
                        f"pv production data (based on {dataType} weather data) for the period between '{tStart.strftime(Constants.DATE_FORMAT)}' and '{tEnd.strftime(Constants.DATE_FORMAT)}' already exists at '{filePath}'."
                    )

                    if toPrint:
                        print(df.loc[ticks])

                    return df.loc[ticks]
                else:
                    toCreateFile = False
            else:
                toCreateFile = True

            if toCreateFile:
                self.logger.log(
                    f"creating file to store pv production data (based on {dataType} weather data) at '{filePath}'."
                )
                df = pd.DataFrame(columns=["tick_unix[ms]"] + self.VARIABLES)
                df.index.name = self.INDEX_NAME
                df.to_csv(filePath)
        else:
            ticks = pd.date_range(
                start=tStart,
                end=tEnd,
                freq=f"{tInt}min",
                tz=Constants.TIME_ZONE_INFO,
            )

        data = pd.DataFrame()

        # Weather data
        data = pd.concat(
            [
                data,
                self.omc.getData(
                    tStart=tStart,
                    tEnd=tEnd,
                    tInt=tInt,
                    isForecast=isForecast,
                    toRecord=False,
                    toPrint=False,
                ),
            ],
            axis=1,
        )

        # Solar position data
        _dfsp = self.location.get_solarposition(
            times=ticks, temperature=data["temperature_2m"]
        )
        if _dfsp.isna().any(axis=1).any():
            raise pd.errors.DataError(
                f"NaN encountered:\n{_dfsp.loc[_dfsp.isna().any(axis=1)]}"
            )
        data = pd.concat([data, _dfsp], axis=1)

        # Irradiation data
        _dfir = pvlib.irradiance.get_total_irradiance(
            surface_tilt=self.surface_tilt,
            surface_azimuth=self.surface_azimuth,
            solar_zenith=data["zenith"],
            solar_azimuth=data["azimuth"],
            dni=data["direct_normal_irradiance"],
            ghi=data["shortwave_radiation"],
            dhi=data["diffuse_radiation"],
            albedo=self.albedo,
            surface_type=self.surface_type,
        )
        if _dfir.isna().any(axis=1).any():
            raise pd.errors.DataError(
                f"NaN encountered:\n{_dfir.loc[_dfir.isna().any(axis=1)]}"
            )
        data = pd.concat([data, _dfir], axis=1)

        # Cell temperature data
        _dfct = (
            pvlib.temperature.sapm_cell(
                poa_global=data["poa_global"],
                temp_air=data["temperature_2m"],
                wind_speed=data["wind_speed_10m"],
                **pvlib.temperature.TEMPERATURE_MODEL_PARAMETERS["sapm"][
                    "open_rack_glass_glass"
                ],
            )
            .rename("cell_temperature")
            .to_frame()
        )
        if _dfct.isna().any(axis=1).any():
            raise pd.errors.DataError(
                f"NaN encountered:\n{_dfct.loc[_dfct.isna().any(axis=1)]}"
            )
        data = pd.concat([data, _dfct], axis=1)

        # DC power data
        _dfpdc = (
            pvlib.pvsystem.pvwatts_dc(
                effective_irradiance=data["poa_global"],
                temp_cell=data["cell_temperature"],
                pdc0=self.pdc0,
                gamma_pdc=self.gamma_pdc,
            )
            .rename("power_dc")
            .to_frame()
        )
        if _dfpdc.isna().any(axis=1).any():
            raise pd.errors.DataError(
                f"NaN encountered:\n{_dfpdc.loc[_dfpdc.isna().any(axis=1)]}"
            )
        data = pd.concat([data, _dfpdc], axis=1)
        data["power_dc"] = data["power_dc"] * self.n_panels

        # AC power data
        _dfpac = (
            pvlib.inverter.pvwatts(
                pdc=data["power_dc"],
                pdc0=self.pdc0 * self.n_panels / self.ratio_dc_ac,
                eta_inv_nom=self.eta_inv,
            )
            .rename("power_ac")
            .to_frame()
        )
        if _dfpac.isna().any(axis=1).any():
            raise pd.errors.DataError(
                f"NaN encountered:\n{_dfpac.loc[_dfpac.isna().any(axis=1)]}"
            )
        data = pd.concat([data, _dfpac], axis=1)
        data = data[self.VARIABLES].copy()

        if toPrint:
            print(data)

        if toRecord:
            self.logger.log(
                f"pv production predicted (based on {dataType} weather data) and recorded for the period between '{tStart.strftime(Constants.DATE_FORMAT)} and {tEnd.strftime(Constants.DATE_FORMAT)}' at a resolution of '{tInt}' minutes."
            )
            df = data.copy()
            dfi = pd.read_csv(filePath, index_col=self.INDEX_NAME, parse_dates=True)
            if not isinstance(dfi.index, pd.DatetimeIndex):
                dfi.index = pd.to_datetime(dfi.index, utc=True).tz_convert(
                    Constants.TIME_ZONE_NAME
                )
            df.drop(index=df.index.intersection(dfi.index), inplace=True)
            cols = df.columns.to_list()
            df["tick_unix[ms]"] = (df.index.astype(np.int64) / 1e6).to_numpy(dtype=int)
            df[["tick_unix[ms]"] + cols].to_csv(filePath, mode="a", header=False)

            # Sort and save
            dfr = pd.read_csv(filePath, index_col=self.INDEX_NAME, parse_dates=True)
            if not isinstance(dfr.index, pd.DatetimeIndex):
                dfr.index = pd.to_datetime(dfr.index, utc=True).tz_convert(
                    Constants.TIME_ZONE_NAME
                )
            dfr.sort_index().to_csv(filePath, mode="w", header=True)

        return data


def update_solarpv_data():
    """continously update solar PV data (based on forecast and historical weather data)"""
    pv716 = SolarPV(
        name="716",
        latitude=55.686,
        longitude=12.101,
        n_panels=46,
        pdc0=395,
        gamma_pdc=-0.004,  # TODO
        ratio_dc_ac=0.9085,  # default: 1.2
        eta_inv=0.96,  # TODO
        surface_tilt=90,
        surface_azimuth=180,
        toLog=False,
    )
    logger = Logger(name="SolarPVDataUpdater", toLog=True)
    logger.log(f"Running...")
    try:
        while True:
            # Weather forecast
            tStart = datetime.now(Constants.TIME_ZONE_INFO)
            if tStart.hour < 14:
                tEnd = (tStart + timedelta(days=1)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) - timedelta(minutes=1)
            elif tStart.hour >= 14:
                tEnd = (tStart + timedelta(days=2)).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) - timedelta(minutes=1)
            pv716.predict(
                tStart=tStart,
                tEnd=tEnd,
                tInt=60,
                isForecast=True,
                toRecord=True,
                toPrint=False,
            )
            logger.log(
                f"Solar PV data (based on forecast weather data) updated until '{tEnd.strftime(Constants.DATE_FORMAT)}'."
            )

            # Historical weather
            tStart = datetime.now(Constants.TIME_ZONE_INFO) + timedelta(days=-1)
            tEnd = datetime.now(Constants.TIME_ZONE_INFO).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(minutes=1)
            pv716.predict(
                tStart=tStart,
                tEnd=tEnd,
                tInt=60,
                isForecast=False,
                toRecord=True,
                toPrint=False,
            )
            logger.log(
                f"Solar PV data (based on historical weather data) updated until '{tEnd.strftime(Constants.DATE_FORMAT)}'."
            )

            nh = 12
            logger.log(f"Pausing for {nh} hours...")
            time.sleep(nh * 60 * 60)

    except KeyboardInterrupt:
        logger.log(f"manual termination.")
        logger.log(f"...terminated")
    except Exception as error:
        logger.log(f"error ({repr(error)}) occurred.")
        logger.log(f"...terminated")
    except:
        logger.log(f"unknown error occurred.")
        logger.log(f"...terminated")


if __name__ == "__main__":
    pass

    update_solarpv_data()

    # --- >>> --- SolarPV --- >>> --- #
    # pv716 = SolarPV(
    #     name="716",
    #     latitude=55.686,
    #     longitude=12.101,
    #     n_panels=46,
    #     pdc0=395,
    #     gamma_pdc=-0.004,  # TODO
    #     ratio_dc_ac=0.9085,  # default: 1.2
    #     eta_inv=0.96,  # TODO
    #     surface_tilt=90,
    #     surface_azimuth=180,
    #     toLog=False,
    # )
    # pv716.predict(
    #     tStart=datetime(2025, 10, 26, tzinfo=Constants.TIME_ZONE_INFO),
    #     tEnd=datetime(2025, 10, 26, 23, tzinfo=Constants.TIME_ZONE_INFO),
    #     tInt=60,
    #     isForecast=False,
    #     toRecord=True,
    #     toPrint=True,
    # )
    # --- <<< --- SolarPV --- <<< --- #
