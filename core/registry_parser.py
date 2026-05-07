import winreg

def is_generated_serial(serial: str) -> bool:
    """Проверяет, сгенерирован ли серийный номер системой (наличие '&' на второй позиции)."""
    return len(serial) > 1 and serial[1] == '&'

def get_registry_value(key, value_name):
    """Безопасное извлечение значения из ключа реестра."""
    try:
        return winreg.QueryValueEx(key, value_name)[0]
    except FileNotFoundError:
        return None

def get_wpd_data():
    """
    Парсит ветку Windows Portable Devices.
    Возвращает словарь, где ключ — часть ID устройства, а значение — FriendlyName.
    """
    wpd_map = {}
    wpd_path = r"SOFTWARE\Microsoft\Windows Portable Devices\Devices"
    try:
        # Ветка WPD находится в HKEY_LOCAL_MACHINE
        base_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, wpd_path)
        num_devices = winreg.QueryInfoKey(base_key)[0]
        
        for i in range(num_devices):
            device_id = winreg.EnumKey(base_key, i)
            with winreg.OpenKey(base_key, device_id) as subkey:
                friendly_name = get_registry_value(subkey, "FriendlyName")
                if friendly_name:
                    # Сохраняем под коротким ключом (серийником), чтобы сопоставить с USBSTOR
                    wpd_map[device_id.upper()] = friendly_name
        winreg.CloseKey(base_key)
    except Exception:
        pass  # Ветка может отсутствовать, если устройства не подключались
    return wpd_map

def get_usbstor_data():
    """Парсит ветку USBSTOR и обогащает данные через WPD."""
    results = []
    base_key_path = r"SYSTEM\CurrentControlSet\Enum\USBSTOR"
    
    # Получаем данные из WPD для корреляции
    wpd_cache = get_wpd_data()
    
    try:
        base_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, base_key_path)
    except Exception as e:
        return [{"error": f"Ошибка доступа к USBSTOR: {e}"}]

    num_devices = winreg.QueryInfoKey(base_key)[0]
    
    for i in range(num_devices):
        try:
            device_str = winreg.EnumKey(base_key, i)
            device_key_path = f"{base_key_path}\\{device_str}"
            device_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, device_key_path)
            
            num_instances = winreg.QueryInfoKey(device_key)[0]
            
            for j in range(num_instances):
                instance_str = winreg.EnumKey(device_key, j)
                instance_key_path = f"{device_key_path}\\{instance_str}"
                instance_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, instance_key_path)
                
                # 1. Пытаемся взять FriendlyName из USBSTOR
                friendly_name = get_registry_value(instance_key, "FriendlyName")
                
                # 2. Если в USBSTOR пусто, ищем в кэше WPD по вхождению серийного номера в ID
                if not friendly_name:
                    for wpd_id, name in wpd_cache.items():
                        if instance_str.upper() in wpd_id:
                            friendly_name = f"{name} (из WPD)"
                            break
                
                if not friendly_name:
                    friendly_name = "Неизвестное устройство"

                parent_id_prefix = get_registry_value(instance_key, "ParentIdPrefix") or "Не найден"
                generated_flag = is_generated_serial(instance_str)

                results.append({
                    "vendor_product": device_str,
                    "serial": instance_str,
                    "friendly_name": friendly_name,
                    "is_generated": generated_flag,
                    "parent_id_prefix": parent_id_prefix
                })
                winreg.CloseKey(instance_key)
            winreg.CloseKey(device_key)
        except OSError:
            continue 
            
    winreg.CloseKey(base_key)
    return results

# Пример вывода
if __name__ == "__main__":
    data = get_usbstor_data()
    for item in data:
        status = "[GEN]" if item.get("is_generated") else "[HW]"
        print(f"{status} {item['vendor_product']}")
        print(f"    SN: {item['serial']}")
        print(f"    Name: {item['friendly_name']}")
        print(f"    ParentPrefix: {item['parent_id_prefix']}\n")
