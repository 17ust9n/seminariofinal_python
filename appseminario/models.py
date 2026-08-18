from django.db import models
from django.core.validators import MinValueValidator

class Supermercado(models.Model):
    ano_fundacion = models.IntegerField()
    cant_sucursales = models.IntegerField()
    pais = models.CharField(max_length=100)

    def __str__(self):
        return f"Supermercado {self.pais}"

class Sucursal(models.Model):
    supermercado = models.ForeignKey(Supermercado, on_delete=models.CASCADE, related_name='sucursales')
    nombre = models.CharField(max_length=150, default="Sin Nombre")
    domicilio = models.CharField(max_length=200, default="Sin Domicilio")
    localidad = models.CharField(max_length=150)
    id_sucursal = models.IntegerField(unique=True)

    def __str__(self):
        return f"{self.nombre} - {self.domicilio} ({self.id_sucursal})"

class Jefe(models.Model):
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='jefes')
    edad = models.IntegerField()
    anos_servicio = models.IntegerField()
    dni = models.IntegerField(unique=True)

    def __str__(self):
        return f"Jefe DNI: {self.dni}"

class Empleado(models.Model):
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='empleados')
    nombre = models.CharField(max_length=150, default="Sin Nombre")
    sexo = models.CharField(max_length=10, default="hombre") 
    edad = models.IntegerField()
    anos_servicio = models.IntegerField()
    dni = models.IntegerField(unique=True)
    id_empleado = models.IntegerField(unique=True)
    sueldo = models.FloatField()

    def __str__(self):
        return f"{self.nombre} (ID: {self.id_empleado})"

class Pasillo(models.Model):
    sucursal = models.ForeignKey(Sucursal, on_delete=models.CASCADE, related_name='pasillos')
    id_pasillo = models.IntegerField(unique=True)

    def __str__(self):
        return f"Pasillo {self.id_pasillo}"

class Producto(models.Model):
    pasillo = models.ForeignKey('Pasillo', on_delete=models.SET_NULL, null=True, blank=True, related_name='productos')
    id_producto = models.IntegerField()
    sucursal_id = models.IntegerField(default=1) 
    nombre = models.CharField(max_length=150)
    empresa = models.CharField(max_length=150)
    peso = models.FloatField(validators=[MinValueValidator(0.0)])
    stock = models.IntegerField(validators=[MinValueValidator(1)])
    categoria = models.CharField(max_length=100)
    costo = models.FloatField()
    imagen = models.ImageField(upload_to='productos/', null=True, blank=True)

    # Conservamos solo el campo estructural para poder armar los combos
    combo_padre = models.ForeignKey(
        'self', 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True, 
        related_name='subproductos'
    )

    class Meta:
        unique_together = ('id_producto', 'sucursal_id') 

    def __str__(self):
        return f"{self.nombre} (Sucursal: {self.sucursal_id})"


class Cliente(models.Model):
    nombre = models.CharField(max_length=150, default="Sin Nombre")
    sexo = models.CharField(max_length=10, default="hombre") 
    edad = models.IntegerField()
    dni = models.IntegerField(unique=True)
    id_cliente = models.IntegerField(unique=True)
    dinero = models.FloatField()

    def __str__(self):
        return self.nombre


class Venta(models.Model):
    METODOS_PAGO_CHOICES = [
        ('contado', 'Al contado'),
        ('efectivo', 'Efectivo'),  # 👈 Incluido aquí para que sea una opción válida
        ('tarjeta_credito', 'Con tarjeta de crédito'),
        ('tarjeta_debito', 'Con tarjeta de débito'),
        ('pago_internet', 'Pago vía Internet'),
        ('transferencia', 'Transferencia bancaria'),
    ]

    id_venta = models.IntegerField(unique=True)
    fecha = models.DateField()
    cant_cuotas = models.IntegerField()
    cantidad = models.IntegerField(default=1) 
    metodo_pago = models.CharField(max_length=30, choices=METODOS_PAGO_CHOICES, default='contado')
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    empleado = models.ForeignKey('Empleado', on_delete=models.PROTECT)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)

    def __str__(self):
        return f"Venta {self.id_venta} - {self.fecha}"
    
    # ❌ SE ELIMINARON LOS MÉTODOS clean() Y save() DE AQUÍ