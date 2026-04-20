import os
import time
import numpy as np
import pandas as pd
import retry_requests
import requests_cache
import openmeteo_requests
from utils import Constants, Logger
from datetime import datetime, timedelta, date


class OpenMeteoClient:
    """Client to retrieve (historical and forecast) weather data from Open-meteo (see https://open-meteo.com/)"""

    FORECAST_API: str = "https://api.open-meteo.com/v1/forecast"
    ARCHIVE_API: str = "https://archive-api.open-meteo.com/v1/archive"
    DAY_FORMAT: str = "%Y-%m-%d"
    INDEX_NAME: str = "tick"
    VARIABLES: list[str] = [
        "temperature_2m",
        "soil_temperature_100_to_255cm",
        "wind_speed_10m",
        "wind_direction_10m",
        "shortwave_radiation",
        "direct_radiation",
        "diffuse_radiation",
        "direct_normal_irradiance",
    ]
    FILENAME: str = f"{os.path.dirname(os.path.abspath(__file__))}/omc_weather"

    def __init__(
        self, location: str, latitude: float, longitude: float, toLog: bool = True
    ):
        self.location = location
        self.latitude = latitude
        self.longitude = longitude
        self.logger = Logger(name="OpenMeteoClient", toLog=toLog)
        return self.logger.log(
            f"initialised for the location '{location}' ({latitude:.3f} N {longitude:.3f} E)."
        )

    def connect(self) -> None:
        self.client = openmeteo_requests.Client(
            session=retry_requests.retry(
                requests_cache.CachedSession(".cache", expire_after=3600),
                retries=5,
                backoff_factor=0.2,
            )
        )
        return self.logger.log(f"connected.")

    def getData(
        self,
        tStart: datetime,
        tEnd: datetime,
        tInt: int,
        isForecast: bool = True,
        toRecord: bool = True,
        toPrint: bool = False,
    ) -> pd.DataFrame:
        """get requested weather data."""

        if isForecast:
            df = pd.DataFrame()
            for day in pd.date_range(start=tStart.date(), end=tEnd.date(), freq="24h"):
                df = pd.concat(
                    [
                        df,
                        self._retrieveForecastData(
                            tStart=day.date(), toRecord=toRecord
                        ),
                    ]
                )
        else:
            df = self._retrieveArchiveData(
                tStart=tStart.date(), tEnd=tEnd.date(), toRecord=toRecord
            )

        if df.isna().any(axis=1).any():
            raise pd.errors.DataError(
                f"NaN encountered:\n{df.loc[df.isna().any(axis=1)]}"
            )

        data = pd.DataFrame(columns=self.VARIABLES)
        data.index.name = self.INDEX_NAME
        for tick in pd.date_range(
            start=tStart.replace(second=0, microsecond=0),
            end=tEnd.replace(second=0, microsecond=0),
            freq=f"{tInt}min",
            tz=Constants.TIME_ZONE_INFO,
        ):
            data.loc[tick] = df.loc[tick.replace(minute=0)].copy()

        if toPrint:
            print(data)

        return data

    def _retrieveForecastData(
        self,
        tStart: date,
        toRecord: bool = True,
        toPrint: bool = False,
    ) -> pd.DataFrame:
        """helper to retrieve hourly weather forecast data."""

        ndays = (tStart - datetime.now(Constants.TIME_ZONE_INFO).date()).days
        if ndays > 1:
            raise ValueError(
                f"weather forecast data retrieval limited to tomorrow (1-day ahead)."
            )
        elif ndays < -90:
            raise ValueError(
                f"weather forecast data available only for the past 90 days."
            )

        filePath = f"{self.FILENAME}_forecast.csv"
        ticks = pd.date_range(
            start=tStart,
            end=tStart + timedelta(days=1),
            freq="1h",
            inclusive="left",
            tz=Constants.TIME_ZONE_INFO,
        )

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
                    f"weather forecast for '{tStart.strftime(Constants.DAY_FORMAT)}' already exists at '{filePath}'."
                )

                if toPrint:
                    print(df.loc[ticks])

                return df.loc[ticks]
            else:
                toCreateFile = False
        else:
            toCreateFile = True

        if toCreateFile and toRecord:
            self.logger.log(
                f"creating file to store weather forecast data at '{filePath}'."
            )
            df = pd.DataFrame(columns=["tick_unix[ms]"] + self.VARIABLES)
            df.index.name = self.INDEX_NAME
            df.to_csv(filePath)

        data = self._retrieveData(tStart=tStart, tEnd=tStart, api="forecast")
        self.logger.log(
            f"weather forecast for '{tStart.strftime(Constants.DAY_FORMAT)}' retrieved."
        )

        if toRecord:
            cols = data.columns.to_list()
            data["tick_unix[ms]"] = (
                (data.index.astype(np.int64) / 1e6).astype(int).to_numpy()
            )
            data[["tick_unix[ms]"] + cols].to_csv(filePath, mode="a", header=False)

            # Sort and save
            dfr = pd.read_csv(filePath, index_col=self.INDEX_NAME, parse_dates=True)
            if not isinstance(dfr.index, pd.DatetimeIndex):
                dfr.index = pd.to_datetime(dfr.index, utc=True).tz_convert(
                    Constants.TIME_ZONE_NAME
                )
            dfr.sort_index().to_csv(filePath, mode="w", header=True)

        if toPrint:
            print(data)

        return data

    def _retrieveArchiveData(
        self, tStart: date, tEnd: date, toRecord: bool = True, toPrint: bool = False
    ) -> pd.DataFrame:
        """helper to retrieve hourly historical weather data."""

        filePath = f"{self.FILENAME}_historical.csv"
        ticks = pd.date_range(
            start=tStart,
            end=tEnd + timedelta(days=1),
            freq="1h",
            inclusive="left",
            tz=Constants.TIME_ZONE_INFO,
        )

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
                    f"historical weather for the period between '{tStart.strftime(Constants.DAY_FORMAT)} and {tEnd.strftime(Constants.DAY_FORMAT)}' already exists at '{filePath}'."
                )

                if toPrint:
                    print(df.loc[ticks])

                return df.loc[ticks]
            else:
                toCreateFile = False
        else:
            toCreateFile = True

        if toCreateFile and toRecord:
            self.logger.log(
                f"creating file to store historical weather data at '{filePath}'."
            )
            df = pd.DataFrame(columns=["tick_unix[ms]"] + self.VARIABLES)
            df.index.name = self.INDEX_NAME
            df.to_csv(filePath)

        data = self._retrieveData(tStart=tStart, tEnd=tEnd, api="archive")
        self.logger.log(
            f"historical weather retrieved for the period between '{tStart.strftime(Constants.DAY_FORMAT)} and {tEnd.strftime(Constants.DAY_FORMAT)}'."
        )

        if toRecord:
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

        if toPrint:
            print(data)

        return data

    def _retrieveData(self, tStart: date, tEnd: date, api: str) -> pd.DataFrame:
        """helper to retrieve hourly weather data through the api."""
        params = {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "hourly": self.VARIABLES,
            "start_date": tStart.strftime(self.DAY_FORMAT),
            "end_date": tEnd.strftime(self.DAY_FORMAT),
            "models": "best_match",
            "wind_speed_unit": "ms",
            "timezone": Constants.TIME_ZONE_NAME,
        }
        if api == "forecast":
            responses = self.client.weather_api(url=self.FORECAST_API, params=params)
        elif api == "archive":
            responses = self.client.weather_api(url=self.ARCHIVE_API, params=params)
        else:
            raise ValueError(f"Invalid api: {api}")

        response = responses[0]
        hourly = response.Hourly()

        start_time = pd.to_datetime(hourly.Time(), unit="s", utc=True).tz_convert(
            Constants.TIME_ZONE_NAME
        )
        interval = pd.Timedelta(seconds=hourly.Interval())
        n = len(hourly.Variables(0).ValuesAsNumpy())


        #  Modified from original to ensure that data is returned only for the requested period (tStart to tEnd) and that the index is properly named and timezone-aware.
        #  Also added error handling for NaN values in the retrieved data.
        data = pd.DataFrame(
            index=pd.date_range(
                start=start_time,
                periods=n,
                freq=interval,
            )
        )
        data.index = data.index.round("1h")
        data.index.rename(self.INDEX_NAME, inplace=True)

        for idx, var in enumerate(self.VARIABLES):
            data[var] = hourly.Variables(idx).ValuesAsNumpy()
        data.dropna(axis=0, how="all", inplace=True)

        ticks = pd.date_range(
            start=tStart,
            end=tEnd + timedelta(days=1),
            freq="1h",
            inclusive="left",
            tz=Constants.TIME_ZONE_INFO,
        )

        if ticks.isin(data.index).all():
            return data
        else:
            raise ValueError(
                f"data unavailable for the period between '{tStart.strftime(Constants.DAY_FORMAT)}' and '{tEnd.strftime(Constants.DAY_FORMAT)}'."
            )


def update_weather_data():
    """continously update weather data (forecast and historical) from Open-meteo (see https://open-meteo.com/)"""
    omc = OpenMeteoClient(
        location="FlexHouse3",
        latitude=55.686,
        longitude=12.101,
        toLog=False,
    )
    omc.connect()
    logger = Logger(name="WeatherDataUpdater", toLog=True)
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
            omc.getData(
                tStart=tStart,
                tEnd=tEnd,
                tInt=60,
                isForecast=True,
                toRecord=True,
                toPrint=False,
            )
            logger.log(
                f"Weather forecast data updated until '{tEnd.strftime(Constants.DATE_FORMAT)}'."
            )

            # Historical weather
            tStart = datetime.now(Constants.TIME_ZONE_INFO) + timedelta(days=-1)
            tEnd = datetime.now(Constants.TIME_ZONE_INFO).replace(
                hour=0, minute=0, second=0, microsecond=0
            ) - timedelta(minutes=1)
            omc.getData(
                tStart=tStart,
                tEnd=tEnd,
                tInt=60,
                isForecast=False,
                toRecord=True,
                toPrint=False,
            )
            logger.log(
                f"Historical weather data updated until '{tEnd.strftime(Constants.DATE_FORMAT)}'."
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

    # update_weather_data()

    # --- >>> --- OpenMeteoClient --- >>> --- #
    # omc = OpenMeteoClient(
    #     location="FlexHouse3",
    #     latitude=55.686,
    #     longitude=12.101,
    #     toLog=False,
    # )
    # omc.connect()
    # omc.getData(
    #     tStart=datetime.now(Constants.TIME_ZONE_INFO) + timedelta(days=-1),
    #     tEnd=datetime.now(Constants.TIME_ZONE_INFO) + timedelta(days=1),
    #     tInt=60,
    #     isForecast=True,
    #     toRecord=False,
    #     toPrint=True,
    # )
    # --- <<< --- OpenMeteoClient --- <<< --- #