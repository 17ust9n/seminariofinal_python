from datetime import date
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import render, get_object_or_404, redirect
from django.db.models import Max
from django.db import transaction  # 👈 AGREGÁ ESTA IMPORTACIÓN AQUÍ
from django.contrib.auth.forms import PasswordChangeForm
from django.db.models import Sum, Q, Count
from django.contrib.auth import login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.db.models.functions import Coalesce
from django.views.decorators.http import require_POST
from django.contrib import messages
from .context_processors import MensajeSingleton 
from django.urls import reverse
from django.utils import timezone
from .models import Producto, Venta, Empleado, Cliente, Sucursal, Jefe
from .forms import RegistroForm
import random


# ========================================================
# 🧩 PATRÓN COMPOSITE (Se queda en la Vista)
# ========================================================
def calcular_precio_composite_manual(producto):
    sub_elementos = producto.subproductos.all()
    if not sub_elementos:
        return producto.costo  # Es una Hoja
    
    total = 0
    for subproducto in sub_elementos:
        total += calcular_precio_composite_manual(subproducto)
    return total


# ========================================================
# VISTA PRINCIPAL CONTROLADORA DE VENTAS
# ========================================================
def vender_producto(request, id_producto):
    sucursal_actual_id = int(request.session.get('sucursal_id', 1))
    producto = get_object_or_404(Producto, id_producto=id_producto, sucursal_id=sucursal_actual_id)

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente')
        empleado_id = request.POST.get('empleado')
        cantidad = int(request.POST.get('cantidad', 1))
        cant_cuotas = int(request.POST.get('cant_cuotas', 1))
        metodo_pago = request.POST.get('metodo_pago', 'contado')

        cliente = get_object_or_404(Cliente, id_cliente=cliente_id)
        empleado = get_object_or_404(Empleado, id_empleado=empleado_id)

        # 1. Aplicación del COMPOSITE para calcular tarifas
        precio_unitario = calcular_precio_composite_manual(producto)
        costo_total = precio_unitario * cantidad

        # 2. Validaciones de Negocio
        if producto.stock < cantidad:
            messages.error(request, f"🚨 Stock insuficiente de '{producto.nombre}'. Disponibles: {producto.stock}")
            return redirect(request.path)

        if cliente.dinero < costo_total:
            messages.error(request, f"❌ El cliente '{cliente.nombre}' no tiene fondos suficientes.")
            return redirect(request.path)

        # 3. Bloque Transaccional Atómico (Solo crea el objeto)
        try:
            with transaction.atomic():
                max_id = Venta.objects.aggregate(max_id=Max('id_venta'))['max_id'] or 0
                nuevo_id_venta = max_id + 1

                # Al guardar este objeto, Django dispara AUTOMÁTICAMENTE la señal de signals.py
                Venta.objects.create(
                    id_venta=nuevo_id_venta,
                    fecha=date.today(),
                    cant_cuotas=cant_cuotas,
                    cantidad=cantidad,
                    metodo_pago=metodo_pago,
                    producto=producto,
                    empleado=empleado,
                    cliente=cliente
                )

            messages.success(request, f"🎉 ¡Venta #{nuevo_id_venta} creada con éxito! El Observer (via Signals) actualizó el stock y las finanzas.")
            return redirect('inicio')

        except Exception as e:
            messages.error(request, f"Hubo un fallo crítico: {e}")
            return redirect(request.path)

    # Lógica para GET (Corregida con la consulta a la Base de Datos)
    clientes = Cliente.objects.all()
    empleados = Empleado.objects.filter(sucursal_id=sucursal_actual_id)
    
    return render(request, 'venta.html', {
        'producto': producto,
        'clientes': clientes,
        'empleados': empleados,
        'metodos_pago': Venta.METODOS_PAGO_CHOICES
    })

# ========================================================
# 🧩 PATRÓN COMPOSITE (Se queda en la Vista)
# ========================================================
def calcular_precio_composite_manual(producto):
    """
    Calcula el precio recorriendo la estructura en árbol.
    Si el producto no tiene subproductos es una HOJA -> devuelve su propio costo.
    Si tiene subproductos es un COMPUESTO -> suma recursivamente los costos de sus hijos.
    """
    sub_elementos = producto.subproductos.all()
    if not sub_elementos:
        return producto.costo  # Es una Hoja
    
    # Es un Compuesto
    total = 0
    for subproducto in sub_elementos:
        total += calcular_precio_composite_manual(subproducto)
    return total


# 🔥 NOTA: LAS FUNCIONES MANUALES DEL OBSERVER FUERON ELIMINADAS DE ACÁ TRASPASADAS A SIGNALS.PY


# ========================================================
# VISTA PRINCIPAL CONTROLADORA DE VENTAS (Versión Limpia)
# ========================================================
def vender_producto(request, id_producto):
    """
    Procesa la venta desde la web aplicando Composite localmente 
    y delegando el Observer al sistema de señales (signals.py).
    """
    sucursal_actual_id = int(request.session.get('sucursal_id', 1))
    
    # Buscamos el producto por su ID propio y la sucursal activa
    producto = get_object_or_404(Producto, id_producto=id_producto, sucursal_id=sucursal_actual_id)

    if request.method == 'POST':
        cliente_id = request.POST.get('cliente')
        empleado_id = request.POST.get('empleado')
        cantidad = int(request.POST.get('cantidad', 1))
        cant_cuotas = int(request.POST.get('cant_cuotas', 1))
        metodo_pago = request.POST.get('metodo_pago', 'contado')

        cliente = get_object_or_404(Cliente, id_cliente=cliente_id)
        empleado = get_object_or_404(Empleado, id_empleado=empleado_id)

        # 1. Aplicación del COMPOSITE para calcular tarifas totales
        precio_unitario = calcular_precio_composite_manual(producto)
        costo_total = precio_unitario * cantidad

        # 2. Validaciones de Negocio explícitas en el flujo
        if producto.stock < cantidad:
            messages.error(request, f"🚨 Stock insuficiente de '{producto.nombre}'. Disponibles: {producto.stock}")
            return redirect(request.path)

        if cliente.dinero < costo_total:
            messages.error(request, f"❌ El cliente '{cliente.nombre}' no tiene fondos suficientes (${cliente.dinero:.2f} de ${costo_total:.2f} requeridos).")
            return redirect(request.path)

        # 3. Bloque Transaccional Atómico
        try:
            with transaction.atomic():
                # Autogeneramos un id de venta correlativo
                max_id = Venta.objects.aggregate(max_id=Max('id_venta'))['max_id'] or 0
                nuevo_id_venta = max_id + 1

                # Almacenamos el registro en la base de datos
                # ⚡ AL GUARDAR AQUÍ, DJANGO DISPARA AUTOMÁTICAMENTE EL OBSERVER EN SIGNALS.PY
                nueva_venta = Venta.objects.create(
                    id_venta=nuevo_id_venta,
                    fecha=date.today(),
                    cant_cuotas=cant_cuotas,
                    cantidad=cantidad,
                    metodo_pago=metodo_pago,
                    producto=producto,
                    empleado=empleado,
                    cliente=cliente
                )

            messages.success(request, f"🎉 ¡Venta #{nuevo_id_venta} creada con éxito! El stock y las finanzas fueron actualizados por el Observer (Signals).")
            return redirect('inicio')

        except Exception as e:
            messages.error(request, f"Hubo un fallo crítico en el servidor de transacciones: {e}")
            return redirect(request.path)

    # Lógica para renderizar por método GET (Carga de listas en el formulario web)
    clientes = Cliente.objects.all()
    # 🔧 Corrección de la consulta para usar tu Base de Datos en lugar de la variable rota 'empleados_data'
    empleados = Empleado.objects.filter(sucursal_id=sucursal_actual_id)
    
    return render(request, 'venta.html', {
        'producto': producto,
        'clientes': clientes,
        'empleados': empleados,
        'metodos_pago': Venta.METODOS_PAGO_CHOICES
    })




def inicio(request):
    """
    Vista de la página de inicio que inyecta la sucursal activa 
    recuperada de la sesión para mostrar su información, mapa y empleados.
    """
    contexto = {}
    
    # Unificamos a 'sucursal_id' para mantener consistencia
    sucursal_id = request.session.get('sucursal_id')
    
    if sucursal_id:
        try:
            sucursal = Sucursal.objects.get(id_sucursal=sucursal_id)
            sucursal.id_sucursal_int = int(sucursal.id_sucursal)
            contexto['sucursal'] = sucursal
            
            # 🔧 SOLUCIÓN: Eliminamos la lista en memoria y filtramos desde la Base de Datos
            # Traemos los empleados cuyo id de sucursal coincida con la activa
            empleados_filtrados = Empleado.objects.filter(sucursal_id=sucursal_id)
            
            # Agregamos la lista de empleados reales al contexto para el template
            contexto['empleados'] = empleados_filtrados

        except Sucursal.DoesNotExist:
            pass

    return render(request, 'inicio.html', contexto)



def acerca(request):
    """
    Muestra la información institucional del proyecto.
    """
    return render(request, 'acerca.html')


def sucursales_view(request):
    if request.method == 'POST':
        sucursal_id = request.POST.get('sucursal_id')
        request.session['sucursal_id'] = sucursal_id 
        return redirect('inicio')

    # 🔧 ANOTACIÓN AGREGADA: Cuenta cuántos empleados tienen asignado el id de cada sucursal
    # Genera un atributo dinámico llamado 'total_empleados' en cada objeto
    sucursales = Sucursal.objects.annotate(total_empleados=Count('empleados'))
    
    # Conservamos tu lógica de coordenadas intacta
    for s in sucursales:
        id_numerico = int(s.id_sucursal)
        if id_numerico == 1: s.coordenadas = "-34.618600,-58.420800"        
        elif id_numerico == 2: s.coordenadas = "-34.604300,-58.396200"        
        elif id_numerico == 3: s.coordenadas = "-34.603500,-58.411100"        
        elif id_numerico == 4: s.coordenadas = "-34.609800,-58.406300"        
        elif id_numerico == 5: s.coordenadas = "-34.623400,-58.413200"        
        else: s.coordenadas = "-34.603700,-58.381600"        

    return render(request, 'sucursales.html', {'sucursales': sucursales})


@login_required
def seleccionar_sucursal(request):
    if request.method == 'POST':
        nueva_sucursal_id = request.POST.get('sucursal_id')
        actual_sucursal_id = request.session.get('sucursal_id')
        
        # 🌟 LOGICA DINÁMICA: Buscamos las instancias en la base de datos para obtener los nombres reales
        nombre_viejo = "Sede Anterior"
        if actual_sucursal_id:
            try:
                nombre_viejo = Sucursal.objects.get(id_sucursal=actual_sucursal_id).nombre
            except Sucursal.DoesNotExist:
                pass
                
        try:
            nombre_nuevo = Sucursal.objects.get(id_sucursal=nueva_sucursal_id).nombre
        except Sucursal.DoesNotExist:
            nombre_nuevo = "Nueva Sede"

        # Aplicamos el cambio físico en la sesión
        request.session['sucursal_id'] = nueva_sucursal_id
        
        # 🌟 EL MENSAJE QUE PEDISTE: Dinámico con f-string origen -> destino
        messages.success(request, f"Se cambió exitosamente de {nombre_viejo} a {nombre_nuevo}.")
        return redirect('inicio')
        
    # 🔧 TU LÓGICA DE ANOTACIÓN Y COORDENADAS SE MANTIENE EXACTAMENTE IGUAL ACÁ ABAJO:
    sucursales = Sucursal.objects.annotate(total_empleados=Count('empleados'))
    
    for s in sucursales:
        id_numerico = int(s.id_sucursal)
        if id_numerico == 1: s.coordenadas = "-34.618600,-58.420800"        
        elif id_numerico == 2: s.coordenadas = "-34.604300,-58.396200"        
        elif id_numerico == 3: s.coordenadas = "-34.603500,-58.411100"        
        elif id_numerico == 4: s.coordenadas = "-34.609800,-58.406300"        
        elif id_numerico == 5: s.coordenadas = "-34.623400,-58.413200"        
        else: s.coordenadas = "-34.603700,-58.381600"        

    return render(request, 'sucursales.html', {'sucursales': sucursales})



def seleccionar_sucursal_empleado(request, id_empleado):
    # 1. Buscamos al empleado de manera segura en la Base de Datos
    empleado = get_object_or_404(Empleado, id_empleado=id_empleado)
    
    # 2. TRAEMOS LAS SUCURSALES DE LA BD CON SU CONTEO REAL
    # Eliminamos los diccionarios harcodeados para que no pisen esta información
    sucursales_con_conteo = Sucursal.objects.annotate(total_empleados=Count('empleados'))
    
    return render(request, 'cambiar_sucursal.html', {
        'empleado': empleado,
        'sucursales': sucursales_con_conteo # Mandamos los objetos de la BD con el atributo .total_empleados
    })


def guardar_sucursal_empleado(request, id_empleado, id_sucursal):
    if request.method == "POST":
        empleado = get_object_or_404(Empleado, id_empleado=id_empleado)
        
        empleado.sucursal_id = int(id_sucursal) 
        empleado.save()
        
        request.session['sucursal_id'] = str(id_sucursal)
        
        # 🔧 USO DEL SINGLETON: Guardamos el mensaje de éxito en la instancia única
        singleton = MensajeSingleton()
        singleton.set_mensaje(f"¡Cambio de sucursal exitoso para el empleado {empleado.nombre}!")
        
        return redirect('lista_usuarios')
        
    return redirect('lista_usuarios')



@login_required
def registrar_venta(request):
    """
    Controlador para CREAR la venta (venta.html).
    Aplica Composite para calcular precios y Observer para actualizar stock/dinero.
    """
    if 'sucursal_id' not in request.session:
        return redirect('seleccionar_sucursal')
        
    sucursal_actual_id = int(request.session['sucursal_id'])

    if request.method == 'POST':
        # ... (Acá va toda la lógica Composite y Observer que pusimos en el paso anterior) ...
        
        try:
            with transaction.atomic():
                # ... (Se crea el objeto Venta y se notifican los observadores) ...
                pass

            messages.success(request, "🎉 Venta registrada con éxito.")
            # Al terminar con éxito, mandamos al usuario a la página de visualización
            return redirect('lista_ventas') 

        except Exception as e:
            messages.error(request, f"Error: {e}")
            return redirect('registrar_venta')

    # Si entra por GET, renderiza el formulario para CREAR la venta
    productos = Producto.objects.filter(sucursal_id=sucursal_actual_id, combo_padre__isnull=True)
    clientes = Cliente.objects.all()
    empleados = Empleado.objects.filter(sucursal_id=sucursal_actual_id)

    return render(request, 'venta.html', { # 👈 Apunta a tu template de creación
        'productos': productos,
        'clientes': clientes,
        'empleados': empleados,
        'metodos_pago': Venta.METODOS_PAGO_CHOICES,
    })


@login_required
def lista_ventas(request):
    """
    Controlador para VISUALIZAR las ventas ya guardadas (lista_ventas.html).
    """
    if 'sucursal_id' not in request.session:
        return redirect('seleccionar_sucursal')
        
    sucursal_actual_id = int(request.session['sucursal_id'])
    
    # Filtramos el historial de ventas que pertenecen a la sucursal activa
    ventas = Venta.objects.filter(producto__sucursal_id=sucursal_actual_id).order_by('-fecha', '-id_venta')
    
    return render(request, 'lista_ventas.html', {'ventas': ventas})


@require_POST
@login_required
def eliminar_Venta(request, pk):
    """
    Anula una transacción comercial y reintegra la cantidad exacta al stock disponible.
    """
    venta = get_object_or_404(Venta, pk=pk)
    producto = venta.producto
    # CORRECCIÓN: Reintegra al stock la cantidad real que se guardó en la venta
    producto.stock += venta.cantidad
    producto.save()
    venta.delete()
    messages.success(request, "Venta anulada y stock restituido correctamente.")
    return redirect('lista_ventas')


def lista_productos(request):
    """
    Vista que renderiza el catálogo agrupado de artículos de la sede activa.
    """
    # 1. Recuperamos el ID activo en la sesión (por defecto el 1 si no hay ninguno)
    sucursal_actual_id = request.session.get('sucursal_id', 1)
    
    # 2. Buscamos la sucursal de forma manual en la lista hardcodeada para el header
    sucursales_data = [
        {"id_sucursal": 1, "nombre": "Sede Almagro", "domicilio": "Venezuela 4343"},
        {"id_sucursal": 2, "nombre": "Sede Da Vinci", "domicilio": "Av. Corrientes 2037"},
        {"id_sucursal": 3, "nombre": "Sede Abasto", "domicilio": "Av. Corrientes 3247"},
        {"id_sucursal": 4, "nombre": "Sede Plaza Miserere (Once)", "domicilio": "Av. Rivadavia 2800"},
        {"id_sucursal": 5, "nombre": "Sede San Cristóbal", "domicilio": "Av. San Juan 3200"},
    ]
    
    sucursal_objeto = None
    for suc in sucursales_data:
        if suc['id_sucursal'] == int(sucursal_actual_id):
            sucursal_objeto = suc
            break

    # 3. CORREGIDO: Filtramos por la sede activa y ORDENAMOS por categoría para el regroup
    from .models import Producto 
    
    # .filter() asegura que solo veas las cosas de tu sucursal.
    # .order_by() agrupa los artículos de la misma categoría de forma consecutiva.
    productos = Producto.objects.filter(sucursal_id=sucursal_actual_id).order_by('categoria', 'nombre')

    # 4. Enviamos todo al template incluyendo la variable 'sucursal' corregida
    return render(request, 'lista_productos.html', {
        'productos': productos,
        'sucursal': sucursal_objeto  # Manda el diccionario de memoria con el nombre exacto
    })




def modificar_producto(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        producto.nombre = request.POST.get('nombre')
        producto.empresa = request.POST.get('empresa')
        producto.categoria = request.POST.get('categoria')
        
        costo_raw = request.POST.get('costo', '').replace(',', '.').strip()
        producto.costo = float(costo_raw) if costo_raw else 0.01
        if producto.costo < 0.01: producto.costo = 0.01

        producto.stock = int(request.POST.get('stock') or 1)
        if producto.stock < 1: producto.stock = 1

        peso_raw = request.POST.get('peso', '').replace(',', '.').strip()
        producto.peso = float(peso_raw) if peso_raw else 0.01
        if producto.peso < 0.01: producto.peso = 0.01
        
        if request.FILES.get('imagen'):
            producto.imagen = request.FILES['imagen']
            
        producto.save()
        messages.success(request, f"{producto.nombre} fue modificado con éxito.")
        return redirect('lista_productos')
        
    return render(request, 'modificar_producto.html', {'producto': producto})


def producto(request):
    max_id = Producto.objects.aggregate(Max('id_producto'))['id_producto__max']
    proximo_id = (max_id + 1) if max_id is not None else 1

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        empresa = request.POST.get('empresa') or "Arcor"
        categoria = request.POST.get('categoria') or "General"
        
        costo_raw = request.POST.get('costo', '').replace(',', '.').strip()
        costo = float(costo_raw) if costo_raw else 0.01
        if costo < 0.01: costo = 0.01

        stock = int(request.POST.get('stock') or 1)
        if stock < 1: stock = 1
        
        peso_raw = request.POST.get('peso', '').replace(',', '.').strip()
        peso = float(peso_raw) if peso_raw else 0.01
        if peso < 0.01: peso = 0.01

        imagen = request.FILES.get('imagen')

        nuevo_prod = Producto(
            id_producto=proximo_id,
            nombre=nombre,
            empresa=empresa,
            categoria=categoria,
            costo=costo,
            stock=stock,
            peso=peso,
            imagen=imagen,
            pasillo=None
        )
        nuevo_prod.save()
        
        messages.success(request, f"Se añadió '{nombre}' a la lista")
        return redirect('lista_productos')

    return render(request, 'producto.html', {'proximo_id': proximo_id})


def detalle_producto(request, pk):
    return redirect('lista_productos')


def vender_producto(request, pk):
    """
    Renderiza el formulario de venta e impacta la transacción afectando
    ÚNICAMENTE al registro de producto de la sucursal activa.
    """
    # get_object_or_404 usa la clave primaria 'pk' de la base de datos (id único de la fila)
    # Por lo tanto, trae el producto específico de la sucursal correcta.
    producto = get_object_or_404(Producto, pk=pk)
    
    total_ventas = Venta.objects.count()
    id_venta_automatico = total_ventas + 1
    
    sucursal_id = request.session.get('sucursal_id') or request.session.get('sucursal_activa')
    empleados_sucursal = Empleado.objects.filter(sucursal_id=sucursal_id)
    
    if empleados_sucursal.exists():
        empleado_asignado = random.choice(list(empleados_sucursal))
    else:
        empleado_asignado = Empleado.objects.first()
        
    clientes = Cliente.objects.all()

    if request.method == 'POST':
        cantidad_unidades = int(request.POST.get('cantidad_unidades', 1))
        cliente_id = request.POST.get('cliente')
        cliente_obj = get_object_or_404(Cliente, id_cliente=cliente_id)
        
        costo_total_compra = producto.costo * cantidad_unidades

        # Validación de stock en la fila de esta sucursal
        if producto.stock < cantidad_unidades:
            messages.error(request, f"Error: Stock insuficiente. El producto {producto.nombre} solo tiene {producto.stock} unidades disponibles en esta sucursal.")
            return redirect('lista_productos')
            
        elif cliente_obj.dinero < costo_total_compra:
            messages.error(request, f"Error: El cliente {cliente_obj.nombre} no tiene suficiente dinero.")
            return redirect('vender_producto', pk=pk)

        else:
            # Crea el registro histórico vinculado al producto exacto de esta sucursal
            Venta.objects.create(
                id_venta=id_venta_automatico,
                fecha=date.today(),
                cantidad=cantidad_unidades,
                cant_cuotas=int(request.POST.get('cant_cuotas', 1)),
                producto=producto,
                empleado=empleado_asignado,
                cliente=cliente_obj,
                metodo_pago=request.POST.get('metodo_pago')
            )
            
            # Resta el stock SOLO de esta sucursal (afecta únicamente a esta fila)
            producto.stock -= cantidad_unidades
            producto.save()
            
            cliente_obj.dinero -= costo_total_compra
            cliente_obj.save()
            
            messages.success(request, f"¡Venta #{id_venta_automatico} registrada con éxito por {cantidad_unidades} unidades!")
            return redirect('lista_ventas')

    context = {
        'producto': producto,
        'productos': Producto.objects.filter(pk=pk),
        'empleado_asignado': empleado_asignado,
        'clientes': clientes,
        'id_venta_automatico': id_venta_automatico,
    }
    return render(request, 'venta.html', context)



@login_required
def eliminar_producto(request, pk):
    producto = get_object_or_404(Producto, pk=pk)
    if request.method == 'POST':
        producto.delete()
        
        # 🎯 Cambiamos el string al mensaje exacto que pediste
        messages.success(request, f"{producto.nombre} se eliminó con éxito.")
        return redirect('lista_productos')
        
    return render(request, 'confirmar_borrado.html', {'producto': producto})



@login_required
@require_POST
def rellenar_stock_producto(request, pk):
    # 1. Buscamos el producto por su ID
    producto = get_object_or_404(Producto, pk=pk)
    
    # 2. Diccionario con los stocks máximos originales (basado en tu carga inicial de datos)
    STOCKS_ORIGINALES = {
        1: 50,   # Sonrisas
        2: 40,   # Criollitas
        3: 100,  # Fideos
        4: 80,   # Agua Villavicencio
        5: 25,   # Vino Tinto
        6: 60,   # Coca Cola
        7: 45,   # Leche La Serenísima
        8: 30,   # Manteca Sancor
        9: 35,   # Shampoo Sedal
    }
    
    # 3. Obtenemos el límite según el id_producto (si no está listado, usa el stock actual como respaldo)
    stock_maximo = STOCKS_ORIGINALES.get(producto.id_producto, producto.stock)
    
    # 4. Asignamos el stock original directamente, asegurando que nunca lo supere
    producto.stock = stock_maximo
    producto.save()
    
    # 5. Volvemos a la lista de productos
    return redirect('lista_productos')


@login_required
def lista_usuarios(request):
    """
    Nómina centralizada de personal local, jefe de sucursal y registros globales de clientes.
    """
    if 'sucursal_id' not in request.session:
        return redirect('seleccionar_sucursal')
        
    sucursal_actual_id = request.session['sucursal_id']
    
    # 1. Buscamos el nombre de la sucursal en tus datos hardcodeados en memoria
    sucursales_data = [
        {"id_sucursal": 1, "nombre": "Sede Almagro", "domicilio": "Venezuela 4343"},
        {"id_sucursal": 2, "nombre": "Sede Da Vinci", "domicilio": "Av. Corrientes 2037"},
        {"id_sucursal": 3, "nombre": "Sede Abasto", "domicilio": "Av. Corrientes 3247"},
        {"id_sucursal": 4, "nombre": "Sede Plaza Miserere (Once)", "domicilio": "Av. Rivadavia 2800"},
        {"id_sucursal": 5, "nombre": "Sede San Cristóbal", "domicilio": "Av. San Juan 3200"},
    ]
    
    sucursal_objeto = None
    for suc in sucursales_data:
        if suc['id_sucursal'] == int(sucursal_actual_id):
            sucursal_objeto = suc
            break

    # 2. RESTAURADO: Consultas reales de base de datos para Empleados y Clientes
    lista_personal = Empleado.objects.filter(sucursal_id=sucursal_actual_id)
    lista_clientes = Cliente.objects.all()
    
    # 3. Buscamos al jefe usando la instancia de base de datos como tenías originalmente
    # Traemos primero el objeto real de la base de datos para que machee con tu modelo Jefe
    from .models import Sucursal
    sucursal_real_bd = Sucursal.objects.filter(id_sucursal=sucursal_actual_id).first()
    
    if sucursal_real_bd:
        lista_jefes = Jefe.objects.filter(sucursal=sucursal_real_bd)
    else:
        lista_jefes = Jefe.objects.none()
    
    # 4. Cruzamos el DNI del jefe con los empleados para obtener Nombre y Sexo
    for jefe in lista_jefes:
        empleado_asociado = Empleado.objects.filter(dni=jefe.dni).first()
        if empleado_asociado:
            jefe.nombre_completo = empleado_asociado.nombre
            jefe.sexo_empleado = empleado_asociado.sexo
        else:
            jefe.nombre_completo = f"Jefe (DNI: {jefe.dni})"
            jefe.sexo_empleado = "hombre"

    # 5. Enviamos todo al template incluyendo tu variable 'sucursal' con los datos en memoria
    return render(request, 'lista_usuarios.html', {
        'lista_personal': lista_personal,
        'lista_jefes': lista_jefes,
        'lista_clientes': lista_clientes,
        'sucursal': sucursal_objeto  # Manda el diccionario de memoria con el nombre exacto
    })



@login_required
def empleado(request):
    """
    Alta de personal asignando de forma transparente la sucursal activa.
    """
    if 'sucursal_id' not in request.session:
        return redirect('seleccionar_sucursal')
        
    sucursal_actual = request.session['sucursal_id']
    proximo_id_empleado = Empleado.objects.count() + 1
    sucursal_instancia = get_object_or_404(Sucursal, id_sucursal=sucursal_actual)

    if request.method == 'POST':
        nombre = request.POST.get('nombre', 'Sin Nombre')
        dni = request.POST.get('dni')
        edad = int(request.POST.get('edad', 0))
        anos_servicio = request.POST.get('anos_servicio')
        sueldo = request.POST.get('sueldo')
        
        if edad < 16:
            messages.error(request, "La ley laboral exige un mínimo de 16 años para trabajar.")
            return render(request, 'empleado.html', {
                'proximo_id_empleado': proximo_id_empleado,
                'sucursal_activa': sucursal_instancia
            })
        
        # Guardamos el registro
        nuevo_empleado = Empleado.objects.create(
            id_empleado=proximo_id_empleado,
            nombre=nombre,
            dni=dni, 
            edad=edad, 
            anos_servicio=anos_servicio,
            sueldo=sueldo, 
            sucursal=sucursal_instancia
        )
        
        # 🌟 MODIFICADO: Nombre dinámico al añadir
        messages.success(request, f'"{nuevo_empleado.nombre}" añadido exitosamente.')
        return redirect('lista_usuarios')
        
    return render(request, 'empleado.html', {
        'proximo_id_empleado': proximo_id_empleado,
        'sucursal_activa': sucursal_instancia
    })


@login_required
def cliente(request):
    """
    Alta de un nuevo cliente comercial.
    """
    proximo_id_cliente = Cliente.objects.count() + 1

    if request.method == 'POST':
        # Capturamos el nombre ingresado (con un valor por defecto seguro)
        nombre = request.POST.get('nombre', 'Cliente Anónimo')
        dni = request.POST.get('dni')
        edad = request.POST.get('edad')
        dinero = request.POST.get('dinero')
        
        # Guardamos el registro
        nuevo_cliente = Cliente.objects.create(
            id_cliente=proximo_id_cliente,
            nombre=nombre,
            edad=edad, 
            dni=dni, 
            dinero=dinero
        )
        
        # 🌟 MODIFICADO: Nombre dinámico al añadir
        messages.success(request, f'"{nuevo_cliente.nombre}" añadido exitosamente.')
        return redirect('lista_usuarios')
        
    return render(request, 'cliente.html', {'proximo_id_cliente': proximo_id_cliente})



@login_required
def detalle_empleado(request, pk):
    empleado = get_object_or_404(Empleado, id_empleado=pk)
    return render(request, 'empleado_detalle.html', {'empleado': empleado})

@login_required
def detalle_cliente(request, pk):
    cliente = get_object_or_404(Cliente, id_cliente=pk)
    return render(request, 'cliente_detalle.html', {'cliente': cliente})



@login_required
def editar_cliente(request, pk):
    """
    Modifica la información de un cliente comercial.
    """
    cliente = get_object_or_404(Cliente, id_cliente=pk)
    
    if request.method == 'POST':
        cliente.nombre = request.POST.get('nombre', cliente.nombre)
        cliente.sexo = request.POST.get('sexo', cliente.sexo)
        cliente.edad = int(request.POST.get('edad', cliente.edad))
        cliente.dinero = float(request.POST.get('dinero', cliente.dinero))
        cliente.save()
        
        # 🌟 MODIFICADO: Nombre dinámico al modificar
        messages.success(request, f'"{cliente.nombre}" modificado exitosamente.')
        return redirect('lista_usuarios')
        
    return render(request, 'modificar_cliente.html', {'cliente': cliente})


@login_required
def editar_empleado(request, pk):
    """
    Modifica la información de un empleado existente.
    """
    empleado = get_object_or_404(Empleado, id_empleado=pk)
    sucursales = Sucursal.objects.all()
    
    if request.method == 'POST':
        empleado.nombre = request.POST.get('nombre', empleado.nombre)
        empleado.sexo = request.POST.get('sexo', empleado.sexo)
        empleado.edad = int(request.POST.get('edad', empleado.edad))
        empleado.anos_servicio = int(request.POST.get('anos_servicio', empleado.anos_servicio))
        empleado.sueldo = float(request.POST.get('sueldo', empleado.sueldo))
        
        sucursal_id = request.POST.get('sucursal')
        if sucursal_id:
            empleado.sucursal_id = int(sucursal_id)
            
        empleado.save()
        
        # 🌟 MODIFICADO: Nombre dinámico al modificar
        messages.success(request, f'"{empleado.nombre}" modificado exitosamente.')
        return redirect('lista_usuarios')
        
    return render(request, 'modificar_empleado.html', {'empleado': empleado, 'sucursales': sucursales})



@login_required
def editar_jefe(request, pk):
    """
    Permite modificar los datos de edad y años de servicio de un jefe específico.
    """
    # CORREGIDO: Línea limpia para traer la instancia del jefe
    jefe = Jefe.objects.filter(id=pk).first()
    
    if not jefe:
        return redirect('lista_usuarios')

    # Buscamos al empleado asociado por DNI para obtener Nombre y Sexo
    empleado_asociado = Empleado.objects.filter(dni=jefe.dni).first()
    if empleado_asociado:
        jefe.nombre_completo = empleado_asociado.nombre
        jefe.sexo_empleado = empleado_asociado.sexo
    else:
        jefe.nombre_completo = f"Jefe (DNI: {jefe.dni})"
        jefe.sexo_empleado = "hombre"

    if request.method == 'POST':
        jefe.edad = int(request.POST.get('edad'))
        jefe.anos_servicio = int(request.POST.get('anos_servicio'))
        jefe.save()
        return redirect('lista_usuarios')

    # CORREGIDO: Render directo que asegura retornar el objeto HttpResponse
    return render(request, 'editar_jefe.html', {'jefe': jefe})


@login_required
def detalle_jefe(request, pk):
    """
    Muestra la ficha técnica detallada de un jefe de sucursal.
    """
    jefe = Jefe.objects.filter(id=pk).first()
    if not jefe:
        return redirect('lista_usuarios')

    # Recuperamos los datos del empleado asociado para complementar el perfil
    empleado_asociado = Empleado.objects.filter(dni=jefe.dni).first()
    if empleado_asociado:
        jefe.nombre_completo = empleado_asociado.nombre
        jefe.sexo_empleado = empleado_asociado.sexo
        jefe.sueldo_base = empleado_asociado.sueldo
    else:
        jefe.nombre_completo = f"Jefe (DNI: {jefe.dni})"
        jefe.sexo_empleado = "hombre"
        jefe.sueldo_base = 0.0

    return render(request, 'jefe_detalle.html', {'jefe': jefe})


# --- VISTAS DE ELIMINACIÓN (UNA SOLA VEZ CADA UNA) ---

@login_required
def eliminar_cliente(request, pk):
    """
    Elimina físicamente un cliente de la base de datos por su ID propio.
    """
    if request.method == 'POST':
        cliente = get_object_or_404(Cliente, id_cliente=pk)
        
        # 🌟 CLAVE: Guardamos el nombre antes de borrar el registro de SQLite
        nombre_guardado = cliente.nombre
        cliente.delete()
        
        # 🌟 MODIFICADO: Nombre dinámico al eliminar
        messages.success(request, f'"{nombre_guardado}" eliminado exitosamente.')
        return redirect('lista_usuarios')
        
    return redirect('lista_usuarios')


@login_required
def eliminar_empleado(request, pk):
    """
    Elimina físicamente un empleado de la base de datos por su ID propio.
    """
    if request.method == 'POST':
        empleado = get_object_or_404(Empleado, id_empleado=pk)
        
        # 🌟 CLAVE: Guardamos el nombre en una variable antes de borrar el objeto de la base de datos
        nombre_guardado = empleado.nombre
        empleado.delete()
        
        # 🌟 MODIFICADO: Nombre dinámico al eliminar
        messages.success(request, f'"{nombre_guardado}" eliminado exitosamente.')
        return redirect('lista_usuarios')
        
    return redirect('lista_usuarios')




@login_required
def ranking_productos_mas_vendidos(request):
    sucursal_id = request.session.get('sucursal_id')
    if not sucursal_id:
        return redirect('seleccionar_sucursal')
        
    # --- 1. PRODUCTOS ---
    productos_mas_vendidos = Producto.objects.filter(
        sucursal_id=sucursal_id
    ).annotate(
        total_vendido=Coalesce(Sum('venta__cantidad'), 0)  # Reemplaza None por 0
    ).order_by('-total_vendido')

    gran_total_unidades = productos_mas_vendidos.aggregate(total_general=Sum('total_vendido'))['total_general'] or 0

    for prod in productos_mas_vendidos:
        if gran_total_unidades > 0 and prod.total_vendido:
            prod.porcentaje_preferencia = round((prod.total_vendido / gran_total_unidades) * 100, 1)
        else:
            prod.porcentaje_preferencia = 0.0


    # --- 2. EMPLEADOS ---
    ranking_empleados = Empleado.objects.filter(
        sucursal__id=sucursal_id
    ).annotate(
        total_unidades_empleado=Coalesce(Sum('venta__cantidad'), 0)  # Reemplaza None por 0
    ).order_by('-total_unidades_empleado')

    for emp in ranking_empleados:
        if gran_total_unidades > 0 and emp.total_unidades_empleado:
            emp.porcentaje_rendimiento = round((emp.total_unidades_empleado / gran_total_unidades) * 100, 1)
        else:
            emp.porcentaje_rendimiento = 0.0


    # --- 3. CLIENTES (SOLUCIÓN DEFINITIVA) ---
    # Usamos Coalesce para que si la suma da vacío (None), asigne un 0 numérico plano.
    # Esto garantiza que el ordenamiento no falle y aparezcan todos en la tabla.
    ranking_clientes = Cliente.objects.annotate(
        total_unidades_cliente=Coalesce(Sum('venta__cantidad'), 0)
    ).order_by('-total_unidades_cliente')

    for cli in ranking_clientes:
        if gran_total_unidades > 0 and cli.total_unidades_cliente:
            cli.porcentaje_fidelidad = round((cli.total_unidades_cliente / gran_total_unidades) * 100, 1)
        else:
            cli.porcentaje_fidelidad = 0.0


    return render(request, 'ranking.html', {
        'productos': productos_mas_vendidos,
        'gran_total_ventas': gran_total_unidades,
        'empleados': ranking_empleados,
        'clientes': ranking_clientes
    })


@login_required
@require_POST
def reiniciar_estadisticas_sucursal(request):
    sucursal_id = request.session.get('sucursal_id')
    if not sucursal_id:
        return redirect('seleccionar_sucursal')

    # CORRECCIÓN: Filtramos y borramos las ventas de los empleados 
    # que pertenecen a la sucursal activa usando la relación 'empleado__sucursal__id'
    Venta.objects.filter(empleado__sucursal__id=sucursal_id).delete()

    # 2. Diccionario estático de tus capacidades máximas originales
    STOCKS_ORIGINALES = {1: 50, 2: 40, 3: 100, 4: 80, 5: 25, 6: 60, 7: 45, 8: 30, 9: 35}

    # 3. Restaurar los stocks de los productos de esta sucursal
    productos = Producto.objects.filter(sucursal_id=sucursal_id)
    for prod in productos:
        prod.stock = STOCKS_ORIGINALES.get(prod.id_producto, prod.stock)
        prod.save()

    # 4. Alerta de confirmación visual para el usuario
    messages.success(request, "Se ha restablecido el stock original y el historial de ventas quedó en cero.")

    return redirect('ranking_productos')


# --- CONTROLADOR DE ACCESO (AUTENTICACIÓN DE USUARIOS) ---
def login_view(request):
    """
    Valida credenciales de acceso y deriva al selector geográfico de sucursales.
    """
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('seleccionar_sucursal')
    else:
        form = AuthenticationForm()
    return render(request, 'usuarios/login.html', {'form': form})


def logout_view(request):
    """
    Destruye la sesión activa eliminando los registros temporales del navegador.
    """
    if request.method == 'POST':
        logout(request)
        messages.success(request, "Sesión cerrada de forma segura.")
        return redirect('login')
    return redirect('inicio')


def registro(request):
    """
    Permite dar de alta nuevos operadores en la plataforma SuperTano.
    """
    if request.method == 'POST':
        form = RegistroForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Usuario registrado de forma exitosa.")
            return redirect('seleccionar_sucursal')
    else:
        form = RegistroForm()
    return render(request, 'usuarios/registro.html', {'form': form})

@login_required
def cambiar_contrasenia(request):
    """
    Vista que procesa el cambio de clave del usuario autenticado,
    validando que la nueva contraseña no coincida con la actual.
    """
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        
        # Validación personalizada de negocio para claves idénticas
        if form.is_valid():
            clave_actual = form.cleaned_data.get('old_password')
            clave_nueva = form.cleaned_data.get('new_password1')
            
            if clave_actual == clave_nueva:
                form.add_error('new_password1', "La nueva contraseña no puede ser idéntica a la contraseña actual.")
            else:
                user = form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Tu contraseña se cambió con éxito.")
                return redirect('lista_usuarios')
    else:
        form = PasswordChangeForm(request.user)
        
    # 🌟 CORREGIDO: Volvemos a buscar el archivo suelto en la raíz de templates
    return render(request, 'cambiar_contrasenia.html', {'form': form})

