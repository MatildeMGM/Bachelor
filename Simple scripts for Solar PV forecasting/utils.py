import os
import sys
import opcua
import pickle
import logging
import platform
import subprocess
import numpy as np
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo


class Symbols:
    """class to store symbols in UTF-8 encoding."""

    DEGREE: str = "\u00b0"


class Constants:
    """class to store constants/common variables."""

    TIME_ZONE_NAME: str = "Europe/Copenhagen"
    TIME_ZONE_INFO: ZoneInfo = ZoneInfo(TIME_ZONE_NAME)
    UTC_ZONE_INFO: ZoneInfo = ZoneInfo("UTC")
    DATE_FORMAT: str = "%d-%m-%Y %H:%M:%S%z"
    DAY_FORMAT: str = "%d-%m-%Y"
    RHO_WATER: float = 988.05  # Water density at 50C [kg/m3]
    CP_WATER: float = 4180  # Water specific heat at 50C [J/kg*K]
    UA_TRUE = opcua.ua.DataValue(opcua.ua.Variant(True, opcua.ua.VariantType.Boolean))
    UA_FALSE = opcua.ua.DataValue(opcua.ua.Variant(False, opcua.ua.VariantType.Boolean))


class Logger:

    def __init__(
        self,
        name: str,
        filename: str = "activity.log",
        toLog: bool = True,
        toPrint: bool = True,
    ):
        self.name = name
        filepath = f"{os.path.dirname(os.path.abspath(__file__))}/{filename}"

        self.logger = logging.getLogger(name=name)
        self.logger.setLevel(level="INFO")
        if toLog:
            fh = logging.FileHandler(
                filename=filepath,
                mode="a",
            )
            fh.setLevel(level="INFO")
            self.logger.addHandler(fh)
        if toPrint:
            sh = logging.StreamHandler(sys.stdout)
            sh.setLevel(level="INFO")
            self.logger.addHandler(sh)
        return

    def log(self, message: str) -> None:
        return self.logger.info(
            f"{datetime.now(Constants.TIME_ZONE_INFO).strftime(Constants.DATE_FORMAT)}: {self.name}: {message}"
        )


class Utilities:

    @classmethod
    def ping_host(cls, host: str) -> bool:
        if platform.system() == "Linux":
            cmd = "-c"
        elif platform.system() == "Windows":
            cmd = "-n"
        else:
            raise ValueError(f"platform: {platform.system()}.")

        output = subprocess.run(
            ["ping", cmd, "1", host], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if output.returncode == 0:
            return True
        else:
            raise ConnectionError(f"host: {host}; return code: {output.returncode}")

    @classmethod
    def convert_flow_rate(
        cls, val: float | np.floating | np.ndarray, fro: str = "l/h", to: str = "kg/s"
    ) -> float | np.floating | np.ndarray:
        """convert flow rate (volumetric and mass) between units."""
        if not isinstance(val, (float, np.floating, np.ndarray)):
            raise TypeError
        if fro == "l/h" and to == "kg/s":
            cval = val / 36e5 * Constants.RHO_WATER
        elif fro == "kg/s" and to == "l/h":
            cval = val * 36 * 1e5 / Constants.RHO_WATER
        elif fro == "m3/h" and to == "kg/s":
            cval = val / 36e2 * Constants.RHO_WATER
        else:
            raise ValueError(f"fro: {fro}; to: {to}.")
        return cval

    @classmethod
    def convert_energy(
        cls, val: float | np.floating | np.ndarray, fro: str = "J", to: str = "kWh"
    ) -> float | np.floating | np.ndarray:
        """convert energy between units."""
        if not isinstance(val, (float, np.floating, np.ndarray)):
            raise TypeError
        if fro == "J" and to == "kWh":
            cval = val / 36e5
        elif fro == "kWh" and to == "J":
            cval = val * 36e5
        else:
            raise ValueError(f"fro: {fro}; to: {to}.")
        return cval

    @classmethod
    def save_data(cls, data: any, fdir: str, fname: str) -> None:
        """save data as a pickle object."""
        if not os.path.exists(fdir):
            os.makedirs(fdir)
        with open(f"{fdir}/{fname}.pkl", "wb") as file:
            pickle.dump(data, file)
        return

    @classmethod
    def load_dict(cls, fdir: str, fname: str) -> dict:
        """load data from a pickle object."""
        with open(f"{fdir}/{fname}.pkl", "rb") as file:
            return pickle.load(file)

    @classmethod
    def round_minute(cls, dt: datetime, interval: int):
        """round minute to nearest interval."""
        if not isinstance(dt, datetime):
            raise TypeError
        if not isinstance(interval, int):
            raise TypeError
        if interval >= 60:
            raise ValueError
        minute = dt.minute
        rounded_minute = (minute // interval) * interval
        return dt.replace(minute=rounded_minute, second=0, microsecond=0)


class InfluxQuery:
    """Class to build flux queries."""

    def __init__(self, bucket: str):
        self.bucket = f'from(bucket: "{bucket}")\n'
        self.range = "|> range(start: tstart, stop: tstop)\n"
        self.pivot = (
            '|> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")\n'
        )
        return

    def buildQuery(self, filters: dict[str, list[str]], aggFunc: str) -> str:
        """build flux query."""
        filter = ""
        for name, elements in filters.items():
            filter += self._buildFilter(name=name, elements=elements)
        if aggFunc not in ["mean", "last"]:
            raise ValueError(f"Invalid aggFun '{aggFunc}'.")
        else:
            filter += f"|> aggregateWindow(every: duration(v: tint), fn: {aggFunc}, createEmpty: false)\n"
        return f"{self.bucket}{self.range}{filter}{self.pivot}"

    @staticmethod
    def _buildFilter(name: str, elements: list[str]) -> str:
        """build the filter function within a flux query."""
        filter = "|> filter(fn: (r) =>"
        for idx, element in enumerate(elements):
            if idx == 0:
                filter += f' r["{name}"] == "{element}"'
            elif idx > 0:
                filter += f' or r["{name}"] == "{element}"'
        filter += ")\n"
        return filter


if __name__ == "__main__":
    pass
    