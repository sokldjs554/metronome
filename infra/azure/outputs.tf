output "public_url" {
  value = "https://${azurerm_container_app.demo.ingress[0].fqdn}"
}

output "environment_id" {
  value = azurerm_container_app_environment.env.id
}
