from django.contrib import admin
from .models import Supermercado, Sucursal, Jefe, Empleado, Pasillo, Producto, Cliente, Venta

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('id_producto', 'nombre', 'peso', 'stock', 'categoria', 'costo')
    # Al ser "categoria" un String/CharField, ahora SÍ podés buscar por él sin errores
    search_fields = ('nombre', 'id_producto', 'categoria')
    list_filter = ('categoria',)

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id_venta', 'fecha', 'producto', 'cliente', 'empleado', 'cant_cuotas')
    list_filter = ('fecha', 'cant_cuotas')
    search_fields = ('id_venta', 'cliente__id_cliente', 'empleado__id_empleado')

# Registro simple para los demás modelos del diagrama
admin.site.register(Supermercado)
admin.site.register(Sucursal)
admin.site.register(Jefe)
admin.site.register(Empleado)
admin.site.register(Pasillo)
admin.site.register(Cliente)