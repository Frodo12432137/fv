-- Historia wszystkich wydań. Parametry ODBC: początek UTC, koniec UTC (wyłączny).
-- Jeśli istnieje rzeczywisty czas odbioru paczki, zwróć go dodatkowo jako available_at (UTC).
SELECT
    punkt AS farm,
    dataGodzinaUTC AS valid_at,
    czasDanychZrodlaCET AS issued_at_local,
    predkoscWiatru AS speed,
    kierunekWiatru AS direction,
    temperatura AS temperature
FROM [PGESA_MarketAnalytics].[wa].[vPogodaPrognoza]
WHERE dataGodzinaUTC >= ? AND dataGodzinaUTC < ?
  AND czasDanychZrodlaCET IS NOT NULL
  AND punkt IN (
    N'Galicja (Hnatkowice – Orzechowce)', N'Galicja (Hnatkowice - Orzechowce)',
    N'Kamieńsk', N'Karnice', N'Karnice II', N'Kisielice', N'Kisielice II',
    N'Karwice', N'Jagniątkowo (Lake Ostrowo)', N'Lotnisko', N'Malbork (Koniecwałd)',
    N'Pelplin', N'Resko I', N'Resko II', N'Rybice', N'Skoczykłody', N'Starza',
    N'Wojciechowo', N'Zalesie', N'Żuromin'
  )
ORDER BY punkt, czasDanychZrodlaCET, dataGodzinaUTC;
