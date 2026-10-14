-- Parametry ODBC: początek dat lokalnych, koniec dat lokalnych (wyłączny).
-- Agregacja turbin w chwili odczytu; agregacja 10 -> 15 minut odbywa się w Pythonie.
-- Kierunek zachowujemy jako średnie sin/cos, nigdy jako AVG(stopni).
WITH NativeReadings AS (
    SELECT [NazwaFarmy] AS farm,
        TRY_CONVERT(datetime2, CONCAT(CONVERT(varchar(10), [Data], 120), ' ',
            COALESCE(CONVERT(varchar(8), [Czas], 108), '00:00:00'))) AS observed_at_local,
        TRY_CONVERT(float, [PredkoscWiatru]) AS speed,
        TRY_CONVERT(float, [KierunekWiatru]) AS direction,
        TRY_CONVERT(float, [Temperatura]) AS temperature
    FROM [PGEEO_DDS].[spss_odczyt].[vFarmyWiatroweDaneMeteoEnergiaBrutto10min]
    WHERE TRY_CONVERT(date, [Data]) >= ? AND TRY_CONVERT(date, [Data]) < ?
      AND [NazwaFarmy] IN (
        N'Galicja', N'Kamieńsk', N'Karnice', N'Karnice II', N'Kisielice', N'Kisielice II',
        N'Karwice', N'Jagniątkowo', N'Lotnisko', N'Malbork', N'Pelplin', N'Resko I',
        N'Resko II', N'Rybice', N'Skoczykłody', N'Starza', N'Wojciechowo', N'Zalesie', N'Żuromin'
      )
)
SELECT farm, observed_at_local,
    AVG(CASE WHEN speed BETWEEN 0 AND 75 THEN speed END) AS speed,
    AVG(CASE WHEN temperature BETWEEN -80 AND 65 THEN temperature END) AS temperature,
    AVG(CASE WHEN direction BETWEEN 0 AND 360 THEN SIN(direction * PI() / 180.0) END) AS obs_direction_sin,
    AVG(CASE WHEN direction BETWEEN 0 AND 360 THEN COS(direction * PI() / 180.0) END) AS obs_direction_cos
FROM NativeReadings
WHERE observed_at_local IS NOT NULL
GROUP BY farm, observed_at_local
ORDER BY farm, observed_at_local;
