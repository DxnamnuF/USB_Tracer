# Wykorzystanie sztucznej inteligencji w projekcie USB_Tracer

Sztuczna inteligencja była wykorzystywana jako narzędzie wspomagające przygotowywanie wstępnych wersji kodu, wykonywanie powtarzalnych zadań i opracowywanie dokumentacji. Poniższe zestawienie powstało na podstawie udostępnionego opisu procesu rozwoju oraz rozmów dotyczących projektu.

## Tworzenie i udoskonalanie kodu

- **Struktura projektu i interfejs wiersza poleceń:** przygotowywanie szkieletów modułów, argumentów uruchomieniowych oraz obsługi błędów w `main.py`.
- **Przetwarzanie artefaktów:** pomoc w przygotowaniu funkcji odczytu rejestru i dzienników Windows, analizy `setupapi.dev.log`, wyodrębniania identyfikatorów urządzeń oraz ujednolicania formatu znaczników czasu. Zadania te dotyczą parserów i modułu `artifact_utils.py`.
- **Łączenie wyników:** opracowywanie propozycji logiki korelacji wpisów, budowania osi czasu i grupowania urządzeń w modułach `timeline_builder.py` i `summary_builder.py`.
- **Generowanie raportów:** pomoc w przygotowaniu szablonów HTML, eksportu do JSON/CSV oraz grafu powiązań w formacie DOT.

## Usprawnienie rutynowych zadań

AI pomagała wyjaśniać komunikaty o błędach, przygotowywać polecenia PowerShell i przykłady uruchomienia, a także redagować i tłumaczyć README oraz instrukcje. Z jej pomocą opracowano również procedurę badania maszyny wirtualnej z systemem Windows: konwersję VDI do VHD, montowanie obrazu w trybie tylko do odczytu oraz przekazywanie programowi ścieżek do zapisanych artefaktów.

