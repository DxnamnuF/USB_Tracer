USB Forensic Tracer - projekt z zakresu DFIR służący do wyszukiwania śladów urządzeń USB w rejestrze systemu Windows.

Skrypt (teraz) analizuje nie standardowe logi .evtx, lecz artefakty znajdujące się w rejestrze:
- HKLM\SYSTEM\CurrentControlSet\Enum\USBSTOR
- HKLM\SOFTWARE\Microsoft\Windows Portable Devices\Devices

Klucz USBSTOR zawiera podstawowe informacje o pamięciach masowych USB, takie jak typ urządzenia, identyfikator vendor/product/revision, numer seryjny, ParentIdPrefix oraz inne identyfikatory systemowe. Klucz Windows Portable Devices wykorzystywany jest jako dodatkowe źródło informacji, które w niektórych przypadkach pozwala uzyskać bardziej czytelną, przyjazną dla użytkownika nazwę urządzenia. Po podłączeniu pamięci USB system Windows pozostawia w rejestrze odpowiednie ślady. Na ich podstawie można ustalić:
- jakie urządzenia USB były podłączane do komputera,
- numer seryjny urządzenia,
- czy numer seryjny jest oryginalny czy został wygenerowany przez system Windows,
- nazwę urządzenia widoczną w systemie,
- klucz rejestru przechowujący dany artefakt,
- czas ostatniej modyfikacji tego klucza.

Należy pamiętać, że pole LastWrite UTC oznacza czas ostatniej zmiany klucza rejestru. Jest to użyteczny znacznik czasu w analizie śledczej, jednak nie zawsze odpowiada dokładnemu momentowi pierwszego lub ostatniego podłączenia urządzenia.

Program działa w systemie Windows przez uruchamianie w terminalu z uprawnieniami administratora.

Eksport wyników:
python main.py --json report.json --csv report.csv

Struktura projektu
main.py – punkt wejściowy programu, interfejs konsolowy oraz obsługa eksportu wyników.
core/registry_parser.py – odczytuje wpisy z USBSTOR i Windows Portable Devices, łączy je ze sobą i zwraca listę słowników zawierających zebrane informacje.

Dalniejszy los
Dodanie analizy logów Microsoft-Windows-Kernel-PnP/Configuration oraz System w celu utworzenia pełniejszej osi czasu (timeline) dotyczącej podłączania urządzeń USB.

