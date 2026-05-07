import sys
from colorama import init, Fore, Style
# Импортируем обновленную функцию парсинга, которая теперь включает корреляцию с WPD
from core.registry_parser import get_usbstor_data 

# Инициализация colorama для корректного отображения цветов в консоли Windows [cite: 36]
init(autoreset=True)

def print_header(text):
    """Отрисовка красивого заголовка в консоли"""
    print(f"\n{Fore.CYAN}{Style.BRIGHT}{'=' * 60}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{text.center(60)}")
    print(f"{Fore.CYAN}{Style.BRIGHT}{'=' * 60}\n")

def main():
    print_header("USB Forensic Tracer - Version 1.5 (WPD Enhanced)")
    print(f"{Fore.WHITE}Запуск анализа системного реестра и корреляция с WPD...{Style.RESET_ALL}\n")
    
    # Получаем данные, которые уже прошли через модуль сопоставления в core/registry_parser.py
    data = get_usbstor_data()
    
    if not data:
        print(f"{Fore.RED}[!] Данные об устройствах не найдены или доступ к реестру ограничен.")
        sys.exit(1)
        
    if isinstance(data, list) and len(data) > 0 and "error" in data[0]:
        print(f"{Fore.RED}[ERROR] {data[0]['error']}")
        print(f"{Fore.YELLOW}Совет: Запустите скрипт от имени Администратора.")
        sys.exit(1)

    print(f"Найдено уникальных артефактов USB: {Fore.GREEN}{len(data)}\n")
    
    for idx, item in enumerate(data, 1):
        # Если имя было подтянуто из WPD, выделяем это для аналитика 
        name_source = ""
        if item.get('wpd_match'):
            name_source = f" {Fore.BLUE}(извлечено из WPD correlation)"
            
        print(f"{Fore.YELLOW}[{idx}] Устройство: {Style.BRIGHT}{item['friendly_name']}{name_source}")
        print(f"    Идентификатор : {item['vendor_product']}")
        
        # Подсветка сгенерированных системой серийников (наличие '&' на 2-й позиции) 
        if item['is_generated']:
            print(f"    Серийный номер: {Fore.RED}{item['serial']} {Fore.RED}{Style.BRIGHT}[СГЕНЕРИРОВАН]")
            print(f"    {Fore.LIGHTBLACK_EX}Примечание: Уникальность этого ID зависит от порта подключения.")
        else:
            print(f"    Серийный номер: {Fore.GREEN}{item['serial']} {Fore.GREEN}[ORIGINAL]")
            
        # Вывод технических связей для дальнейшего анализа
        print(f"    ParentIdPrefix: {Fore.WHITE}{item['parent_id_prefix']}")
        
        # Если есть VSN (Volume Serial Number) из WPD, выводим его (если добавлено в parser)
        if item.get('volume_serial'):
            print(f"    Volume Serial : {Fore.CYAN}{item['volume_serial']}")
            
        print(f"{Fore.LIGHTBLACK_EX}{'-' * 60}")

    print(f"\n{Fore.GREEN}[+] Анализ завершен успешно.")

if __name__ == "__main__":
    # Рекомендуется запуск от имени Администратора для доступа ко всем веткам реестра 
    main()
